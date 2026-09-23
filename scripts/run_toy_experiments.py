#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from jsonschema import validate

from uliana.baselines import camera_only, force_only, fused
from uliana.config import load_config
from uliana.reliability import assess
from uliana.scoring import component_scores
from uliana.session import summarize, write_jsonl
from uliana.simulator import generate_experiment
from uliana.state_machine import PushUpStateMachine
from uliana.synchronization import synchronize
from uliana.types import AnalysisResult

OUT = ROOT / "artifacts" / "toy_experiments"
SYSTEMS = {"camera_only": camera_only, "force_only": force_only, "fused": fused}


def technique_ground_truth(scenario: str) -> str:
    if scenario.startswith("left_overload"):
        return "shift_right"
    if scenario.startswith("right_overload"):
        return "shift_left"
    if "insufficient_depth" in scenario:
        return "depth"
    if "body_line_error" in scenario:
        return "alignment"
    return "good"


def expected_abstention(scenario: str, system: str) -> bool:
    force_bad = scenario in {"missing_force_samples", "delayed_force_samples", "sensor_saturation", "near_zero_total_force"}
    return (system in {"force_only", "fused"} and force_bad) or (system in {"camera_only", "fused"} and scenario == "low_pose_confidence")


def cue_class(cue: str, abstained: bool) -> str:
    lower = cue.lower()
    if abstained:
        return "abstain"
    if "right" in lower: return "shift_right"
    if "left" in lower: return "shift_left"
    if "depth" in lower: return "depth"
    if "straight" in lower: return "alignment"
    return "good"


def macro_f1(rows: list[dict]) -> float:
    labels = sorted({r["expected"] for r in rows} | {r["predicted"] for r in rows})
    scores = []
    for label in labels:
        tp = sum(r["expected"] == label == r["predicted"] for r in rows)
        fp = sum(r["expected"] != label and r["predicted"] == label for r in rows)
        fn = sum(r["expected"] == label and r["predicted"] != label for r in rows)
        scores.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0)
    return sum(scores) / len(scores) if scores else 0


def evaluate(config: dict, severity: float = 1.0, evaluation_participants: set[int] | None = None):
    rows, sync_rows, packets, rep_errors = [], [], [], []
    repetitions = generate_experiment(config, severity)
    for index, repetition in enumerate(repetitions, 1):
        if evaluation_participants is not None and repetition.participant_id not in evaluation_participants:
            continue
        synced, sync_stats = synchronize(repetition.pose_samples, repetition.force_samples, config["synchronization"]["max_difference_ms"], config["smoothing"]["window_samples"])
        sync_rows.append(sync_stats)
        summary = summarize(index, synced, config["reliability"]["min_total_force_n"], config["thresholds"])
        reliability = assess(synced, config)
        machine = PushUpStateMachine(**config["state_machine"])
        for sample in repetition.pose_samples:
            machine.update(sample.elbow_angle_deg)
        rep_errors.append(abs(machine.rep_count - 1))
        scores = component_scores(summary, config)
        decisions = {name: fn(summary, reliability, config) for name, fn in SYSTEMS.items()}
        for name, decision in decisions.items():
            expected = technique_ground_truth(repetition.scenario)
            predicted = cue_class(decision.cue, decision.abstained)
            should_abstain = expected_abstention(repetition.scenario, name)
            rows.append({
                "participant_id": repetition.participant_id, "rep_id": index, "scenario": repetition.scenario,
                "system": name, "technique_ground_truth": expected, "predicted": predicted,
                "technique_correct": int(not decision.abstained and expected == predicted),
                "expected_abstention": int(should_abstain), "abstention_correct": int(decision.abstained == should_abstain),
                "abstained": int(decision.abstained), "quality": scores["overall"], "rep_count": machine.rep_count,
                "sync_percent": round(sync_stats["synchronized_percent"], 3), "sync_mean_ms": sync_stats["mean_error_ms"],
            })
        decision = decisions["fused"]
        last = synced[-1]
        force = last.force
        packets.append(AnalysisResult(
            "1.0", "toy_simulator", f"toy-p{repetition.participant_id:02d}", last.pose.timestamp_ms, index, "up",
            {"left_force_n": round(force.left_force_n, 1) if force else 0.0, "right_force_n": round(force.right_force_n, 1) if force else 0.0,
             "asymmetry_percent": round(summary.mean_asymmetry_percent or 0, 1), "elbow_angle_deg": round(last.pose.elbow_angle_deg, 1),
             "body_line_error_deg": round(summary.maximum_body_line_error_deg, 1)}, scores, asdict(decision)))
    return rows, sync_rows, packets, rep_errors


def aggregate(rows: list[dict], sync_rows: list[dict], rep_errors: list[int]) -> dict:
    systems = {}
    for name in SYSTEMS:
        subset = [r for r in rows if r["system"] == name]
        acted = [r for r in subset if not r["abstained"]]
        deliberate = [r for r in subset if r["expected_abstention"]]
        directional = [r for r in subset if r["technique_ground_truth"].startswith("shift")]
        f1_rows = [{"expected": r["technique_ground_truth"], "predicted": r["predicted"]} for r in subset]
        systems[name] = {
            "technique_classification_accuracy_all_cases": sum(r["technique_correct"] for r in subset) / len(subset),
            "macro_f1_all_cases": macro_f1(f1_rows),
            "feedback_direction_accuracy_all_directional_cases": sum(r["technique_correct"] for r in directional) / len(directional) if directional else None,
            "decision_coverage": len(acted) / len(subset),
            "selective_error_rate_answered_cases": 1 - sum(r["technique_correct"] for r in acted) / len(acted) if acted else None,
            "expected_abstention_recall": sum(r["abstained"] for r in deliberate) / len(deliberate) if deliberate else None,
            "abstention_behavior_accuracy_all_cases": sum(r["abstention_correct"] for r in subset) / len(subset),
        }
    errors = [s["mean_error_ms"] for s in sync_rows if s["mean_error_ms"] is not None]
    per_scenario = {}
    for scenario in sorted({r["scenario"] for r in rows}):
        per_scenario[scenario] = {}
        for name in SYSTEMS:
            subset = [r for r in rows if r["scenario"] == scenario and r["system"] == name]
            answered = [r for r in subset if not r["abstained"]]
            per_scenario[scenario][name] = {"cases": len(subset),
                "accuracy_all_cases": sum(r["technique_correct"] for r in subset) / len(subset),
                "coverage": len(answered) / len(subset),
                "selective_error": 1 - sum(r["technique_correct"] for r in answered) / len(answered) if answered else None}
    return {"evaluation_repetitions": len(rep_errors), "mean_rep_count_error": sum(rep_errors) / len(rep_errors), "systems": systems,
            "per_scenario": per_scenario,
            "synchronization": {"mean_error_ms": sum(errors) / len(errors),
                                "mean_synchronized_percent": sum(s["synchronized_percent"] for s in sync_rows) / len(sync_rows),
                                "missing_matches": sum(s["missing_matches"] for s in sync_rows)}}


def write_report(metrics: dict, scenario_rows: list[dict], robustness: list[dict]) -> None:
    table = ["| System | All-case accuracy | Macro-F1 | Coverage | Selective error | Expected-abstention recall |", "|---|---:|---:|---:|---:|---:|"]
    for name, values in metrics["systems"].items():
        table.append(f"| {name} | {values['technique_classification_accuracy_all_cases']:.3f} | {values['macro_f1_all_cases']:.3f} | {values['decision_coverage']:.3f} | {values['selective_error_rate_answered_cases']:.3f} | {values['expected_abstention_recall']:.3f} |")
    report = f"""# ULIANA toy experiment report

## Experiment objective

Validate deterministic implementation behaviour for one push-up, two force channels, one camera, one score and one reliability-gated cue.

## Data-generation assumptions

Thirty synthetic participants perform twenty repetitions sampled at 50 Hz force and 30 Hz pose. Participant body weight, tempo, baseline asymmetry and noise vary. The first 10 participant IDs are reserved as a calibration partition; fixed configuration thresholds are evaluated only on participant IDs 10–29. No thresholds are fitted on evaluation repetitions.

## Compared systems

Camera-only observes pose, force-only observes handles, and fused observes both through the same reliability layer. All systems use the same technique ground truth. Reliability expectations differ only where a system actually depends on an unavailable modality; missing force does not invalidate camera-only.

## Results

{chr(10).join(table)}

Mean repetition-count error: **{metrics['mean_rep_count_error']:.3f}**. Mean synchronized observations: **{metrics['synchronization']['mean_synchronized_percent']:.1f}%**; mean matched timestamp error: **{metrics['synchronization']['mean_error_ms']:.2f} ms**.

Per-scenario results are in `scenario_results.csv`; increasing-noise results are in `robustness.png` and `metrics.json`.

All-case accuracy and macro-F1 use every held-out repetition; an abstention is an unanswered classification and is therefore incorrect. Coverage is answered/all cases. Selective error is wrong answers/answered cases. Direction accuracy is correct shift direction/all cases whose shared technique truth requires a shift. Expected-abstention recall is correct abstentions/cases deliberately unreliable for that system.

## Failure cases

Combined-error scenarios yield only the highest-priority cue. Camera-only cannot directly identify force imbalance; force-only cannot identify depth, alignment, or low camera confidence. Severe timing delay and missing force deliberately trigger abstention. Added noise can prevent complete state transitions or reduce synchronization coverage.

## What the experiment proves

The code reproducibly generates synchronized labelled toy signals, detects cycles, keeps modality boundaries, emits schema-compatible packets, and follows the configured reliability/feedback priorities on synthetic cases.

## What it does not prove

Synthetic accuracy is not scientific evidence of real-user effectiveness, injury prevention, clinical benefit, force accuracy, pose accuracy, or validated thresholds. This is not a medical device or injury-risk estimator.

## Requirements for real-data validation

Calibrated load cells, timestamp characterization, consented participant recordings, a labelled trainer protocol, participant-wise held-out evaluation, demographic/pose-condition coverage, and latency/reliability measurements are still required.

## Recommended next technical step

Replay one synchronized recorded push-up from calibrated load cells and a pretrained pose estimator through these unchanged contracts, retaining raw observations and comparing outputs with manually labelled events.
"""
    (OUT / "report.md").write_text(report, encoding="utf-8")


def main() -> None:
    config = load_config(ROOT / "configs" / "toy_experiment.json")
    OUT.mkdir(parents=True, exist_ok=True)
    evaluation_ids = set(range(10, config["participants"]))
    rows, sync_rows, packets, rep_errors = evaluate(config, evaluation_participants=evaluation_ids)
    metrics = aggregate(rows, sync_rows, rep_errors)
    robustness = []
    for severity in (0.5, 1.0, 2.0, 4.0):
        rr, ss, _, ee = evaluate(config, severity, evaluation_ids)
        mm = aggregate(rr, ss, ee)
        robustness.append({"severity": severity, "fused_accuracy": mm["systems"]["fused"]["technique_classification_accuracy_all_cases"],
                           "rep_error": mm["mean_rep_count_error"], "sync_percent": mm["synchronization"]["mean_synchronized_percent"]})
    metrics["robustness"] = robustness
    metrics["interpretation"] = "Synthetic labels demonstrate implementation behaviour, not real-world effectiveness."
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    fields = list(rows[0])
    with (OUT / "scenario_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    summary_rows = []
    for system in SYSTEMS:
        for scenario in config["scenarios"]:
            subset = [r for r in rows if r["system"] == system and r["scenario"] == scenario]
            answered = [r for r in subset if not r["abstained"]]
            summary_rows.append({"system": system, "scenario": scenario, "cases": len(subset),
                "accuracy_all_cases": sum(r["technique_correct"] for r in subset) / len(subset),
                "coverage": len(answered) / len(subset),
                "selective_error": 1 - sum(r["technique_correct"] for r in answered) / len(answered) if answered else "undefined",
                "mean_quality": sum(r["quality"] for r in subset) / len(subset)})
    with (OUT / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0])); writer.writeheader(); writer.writerows(summary_rows)
    schema = json.loads((ROOT / "schemas" / "analysis-result.schema.json").read_text(encoding="utf-8"))
    for packet in packets:
        validate(packet.to_dict(), schema)
        json.dumps(packet.to_dict(), allow_nan=False)
    write_jsonl(OUT / "sample_session.jsonl", packets[:20])
    grouped = defaultdict(list)
    for row in rows:
        if row["system"] == "fused": grouped[row["scenario"]].append(row["quality"])
    labels = list(grouped)
    plt.figure(figsize=(11, 5)); plt.bar(labels, [sum(grouped[x]) / len(grouped[x]) for x in labels]); plt.xticks(rotation=55, ha="right"); plt.ylabel("Mean toy quality"); plt.tight_layout(); plt.savefig(OUT / "quality_by_scenario.png"); plt.close()
    plt.figure(figsize=(7, 4)); plt.plot([x["severity"] for x in robustness], [x["fused_accuracy"] for x in robustness], marker="o", label="Fused accuracy"); plt.plot([x["severity"] for x in robustness], [x["sync_percent"] / 100 for x in robustness], marker="o", label="Sync fraction"); plt.xlabel("Noise / jitter / missingness multiplier"); plt.ylim(0, 1.05); plt.legend(); plt.tight_layout(); plt.savefig(OUT / "robustness.png"); plt.close()
    write_report(metrics, rows, robustness)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
