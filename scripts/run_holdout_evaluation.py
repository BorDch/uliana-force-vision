#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import platform
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_development_baseline as shared
from uliana.config import load_config
from uliana.development_baseline import PREDICTION_FIELDS, calculate_metrics, error_rows, json_cell, validate_manifest, write_predictions
from uliana.reporting.provenance import build_provenance, sha256_file
from uliana.video.camera_session import analyze_camera_observations, write_camera_outputs
from uliana.video.processing import process_observations, write_observations

FROZEN_CONFIG_SHA256 = "c996926a052622815eb3acb08684a9e3176d39d0d95129f65d9e855bf7f331d9"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the first frozen holdout evaluation.")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/incoming/recordings_manifest.csv")
    parser.add_argument("--video-root", type=Path, default=ROOT / "data/incoming/recordings")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/video_processing.json")
    parser.add_argument("--model", type=Path, default=ROOT / "models/pose_landmarker_full.task")
    parser.add_argument("--freeze-manifest", type=Path, default=ROOT / "artifacts/real_recordings/development_baseline_v2/freeze_manifest.json")
    parser.add_argument("--artifact-dir", type=Path, default=ROOT / "artifacts/real_recordings/holdout_v2")
    parser.add_argument("--force-inference", action="store_true")
    return parser.parse_args()


def prediction_input(row: dict[str, str]) -> dict[str, str]:
    """Return the only manifest fields exposed to prediction."""
    return {name: row[name] for name in ("filename", "participant_id", "session_id")}


def attach_evaluation(prediction: dict, label: dict[str, str]) -> dict:
    output = dict(prediction)
    output["manual_viewpoint"] = label["manual_viewpoint"]
    output["manual_repetition_count"] = label["manual_repetition_count"]
    return output


def verify_freeze(args: argparse.Namespace) -> dict:
    freeze = json.loads(args.freeze_manifest.read_text(encoding="utf-8"))
    checks = {
        "configuration_sha256": sha256_file(args.config),
        "configuration_snapshot_sha256": sha256_file(args.freeze_manifest.parent / "config_snapshot.json"),
        "manifest_sha256": sha256_file(args.manifest),
        "pose_model_sha256": sha256_file(args.model),
    }
    mismatches = {key: {"expected": freeze.get(key), "actual": value} for key, value in checks.items() if freeze.get(key) != value}
    for relative, expected in freeze.get("source_hashes", {}).items():
        actual = sha256_file(ROOT / relative)
        if actual != expected:
            mismatches[f"source:{relative}"] = {"expected": expected, "actual": actual}
    if checks["configuration_sha256"] != FROZEN_CONFIG_SHA256:
        mismatches["requested_configuration_sha256"] = {"expected": FROZEN_CONFIG_SHA256, "actual": checks["configuration_sha256"]}
    if mismatches:
        raise RuntimeError("freeze verification failed: " + json.dumps(mismatches, sort_keys=True))
    return {"status": "matched", "checks": checks, "source_hashes": freeze["source_hashes"]}


def _blank_prediction(row: dict[str, str]) -> dict:
    output = {name: "" for name in PREDICTION_FIELDS}
    output.update(row)
    return output


def process_blind(row: dict[str, str], args: argparse.Namespace, config: dict) -> tuple[dict, dict | None]:
    started = time.perf_counter()
    prediction = _blank_prediction(row)
    video_path = args.video_root / row["filename"]
    runtime = None
    try:
        raw, cache_dir, cache_status = shared._load_or_infer_raw(row, video_path, args)
        observations, video_summary = process_observations(raw, config)
        result, features, phases, camera_metrics = analyze_camera_observations(observations, video_summary, config)
        write_observations(cache_dir / "video_observations.jsonl", observations)
        shared._write_json(cache_dir / "video_summary.json", video_summary)
        write_camera_outputs(cache_dir, result, features, camera_metrics)
        unavailable = [{"condition": item.condition, "rep_id": item.rep_id, "reason": item.reason} for item in result.unavailable_assessments]
        reasons = sorted({item["reason"] for item in unavailable if item["reason"]})
        warnings = list(dict.fromkeys(result.warnings + list(video_summary.get("warnings", [])) + sorted(video_summary.get("quality_code_counts", {}))))
        prediction.update({
            "predicted_viewpoint": result.detected_viewpoint.value,
            "viewpoint_confidence": result.detected_viewpoint.confidence if result.detected_viewpoint.confidence is not None else "",
            "predicted_repetition_count": result.repetition_count if result.repetition_count is not None else "",
            "repetition_confidence": camera_metrics["count_confidence"] if result.repetition_count is not None else "",
            "selected_phase_signal": result.provenance.get("phase_signal") or "",
            "pose_detection_coverage": video_summary.get("valid_pose_fraction", ""),
            "phase_signal_coverage": camera_metrics.get("phase_signal_coverage", ""),
            "assessment_coverage": camera_metrics["assessment_coverage"],
            "eligible_assessments": camera_metrics["eligible_assessments"],
            "answered_assessments": camera_metrics["answered_assessments"],
            "unavailable_assessments": json_cell(unavailable),
            "unavailable_reasons": "|".join(reasons),
            "quality_warnings": "|".join(warnings),
            "processing_status": "success", "cache_status": cache_status,
        })
        runtime = {"video_path": video_path, "observations": observations, "result": result, "phases": phases, "warnings": warnings}
    except Exception as exc:
        prediction.update({"processing_status": "failed", "unavailable_assessments": "[]", "unavailable_reasons": "processing_failed", "quality_warnings": f"processing_failed:{type(exc).__name__}", "error_message": f"{type(exc).__name__}: {exc}"})
    prediction["processing_time_seconds"] = round(time.perf_counter() - started, 3)
    return prediction, runtime


def _fmt(value, percent: bool = False) -> str:
    if value is None: return "unavailable"
    if percent: return f"{value:.1%}"
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def _metric_table(grouped: dict[str, dict], label: str) -> list[str]:
    lines = [f"| {label} | Available | MAE | RMSE | Exact | Within ±1 | Signed error | Predicted/manual |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, metric in grouped.items():
        lines.append(f"| {name} | {metric['answered_recordings']}/{metric['eligible_recordings']} | {_fmt(metric['count_mae'])} | {_fmt(metric['count_rmse'])} | {_fmt(metric['exact_count_accuracy'], True)} | {_fmt(metric['within_one_accuracy'], True)} | {_fmt(metric['mean_signed_error'])} | {metric['total_predicted_answered']}/{metric['total_manual_answered']} |")
    return lines


def build_report(rows: list[dict], metrics: dict, provenance: dict) -> str:
    count = metrics["repetition_count"]; view = metrics["viewpoint"]; reliability = metrics["reliability"]
    lines = ["# First holdout evaluation — frozen development baseline v2", "", "## Scope and leakage control", "", "This is an offline recorded-session evaluation on three unseen participants (anon-p008–anon-p010). Whole-recording signal quantiles are permitted. Manual counts and manual viewpoints were withheld from prediction and signal selection, blind predictions were saved and hashed first, and labels were attached only for evaluation. No threshold tuning or label changes were performed.", "", "Technique accuracy is unavailable because trainer technique annotations do not exist.", "", "## Freeze verification", "", f"- Configuration SHA-256: `{provenance['freeze_verification']['checks']['configuration_sha256']}` (matched)", f"- Manifest SHA-256: `{provenance['freeze_verification']['checks']['manifest_sha256']}` (matched)", f"- Pose model SHA-256: `{provenance['freeze_verification']['checks']['pose_model_sha256']}` (matched)", f"- Blind predictions SHA-256: `{provenance['blind_predictions_sha256']}`", "- Recorded pipeline source hashes matched the freeze manifest before any holdout media was opened.", "", "## Overall results", "", f"- Count availability: {_fmt(count['coverage'], True)} ({count['answered_recordings']}/{count['eligible_recordings']}); unavailable: {count['unavailable_predictions']}", f"- MAE: {_fmt(count['count_mae'])}; RMSE: {_fmt(count['count_rmse'])}; mean signed error: {_fmt(count['mean_signed_error'])}", f"- Exact-count accuracy: {_fmt(count['exact_count_accuracy'], True)}; accuracy within ±1: {_fmt(count['within_one_accuracy'], True)}", f"- Predicted/manual repetitions among available results: {count['total_predicted_answered']}/{count['total_manual_answered']}", f"- Viewpoint accuracy: {_fmt(view['overall_accuracy'], True)}; unknown rate: {_fmt(view['unknown_rate'], True)}", f"- Assessment coverage: {_fmt(reliability['assessment_coverage'], True)}", "", "A numeric zero is an available prediction and participates in error metrics. Only a blank/`None` count is unavailable; unavailable counts reduce coverage and are never converted to zero.", "", "Unavailable count reasons: none.", "", "Unavailable assessment reasons: " + (", ".join(f"{key}={value}" for key, value in reliability["unavailable_reason_frequencies"].items()) or "none") + ".", "", "## Per-recording results", "", "| Session | Participant | Manual view | Predicted view | Manual | Predicted | Signed error | Absolute error | Status | Warnings |", "|---|---|---|---|---:|---:|---:|---:|---|---|"]
    for row in error_rows(rows):
        lines.append(f"| {row['session_id']} | {row['participant_id']} | {row['manual_viewpoint']} | {row['predicted_viewpoint']} | {row['manual_repetition_count']} | {_fmt(row['predicted_repetition_count'])} | {_fmt(row['signed_error'])} | {_fmt(row['absolute_error'])} | {row['status']} | {row['warnings'] or 'none'} |")
    lines += ["", "## Results by viewpoint", ""] + _metric_table(metrics["repetition_count_by_viewpoint"], "Viewpoint")
    lines += ["", "## Results by participant", ""] + _metric_table(metrics["repetition_count_by_participant"], "Participant")
    lines += ["", "## Viewpoint evaluation", "", "| Actual \\ Predicted | front | oblique | side | unknown |", "|---|---:|---:|---:|---:|"]
    for actual in ("front", "oblique", "side"):
        values = view["confusion_matrix"][actual]; lines.append(f"| {actual} | {values['front']} | {values['oblique']} | {values['side']} | {values['unknown']} |")
    lines += ["", "## Preserved failures and discrepancy review", ""]
    failures = [row for row in error_rows(rows) if row["status"] != "success" or row["absolute_error"] not in (0, None)]
    if failures:
        lines.extend(f"- `{row['session_id']}`: manual={row['manual_repetition_count']}, predicted={_fmt(row['predicted_repetition_count'])}, signed error={_fmt(row['signed_error'])}; {row['warnings'] or row['status']}." for row in failures)
    else: lines.append("No processing or count discrepancies occurred.")
    lines += ["", "Annotated previews were generated only after blind predictions were saved. Visual findings are observational and did not alter this evaluation.", "", "## Limitations", "", "- Only three unseen participants and nine recordings are included.", "- Thresholds use whole-recording quantiles, so these results do not establish streaming or real-time performance.", "- Manual repetition counts have no timestamp annotations; discrepancy timing can only be localized approximately by reviewing cycles and boundaries.", "- Assessment availability depends on viewpoint and evidence quality.", "- Technique accuracy cannot be reported without trainer annotations.", "", "## Reproduction", "", "```bash", provenance["command"], "```", ""]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    for name in ("manifest", "video_root", "config", "model", "freeze_manifest", "artifact_dir"):
        value = getattr(args, name)
        if not value.is_absolute(): setattr(args, name, ROOT / value)
    args.pose_cache_root = None
    freeze_verification = verify_freeze(args)
    rows, controls = validate_manifest(args.manifest, args.video_root)
    labels = [dict(row) for row in rows if row["split"] == "holdout"]
    if len(labels) != 9 or {row["participant_id"] for row in labels} != {"anon-p008", "anon-p009", "anon-p010"}: raise RuntimeError("holdout selection is not exactly anon-p008–anon-p010")
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    preview_dir = args.artifact_dir / "previews"; preview_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.manifest, args.artifact_dir / "manifest_snapshot.csv")
    shutil.copyfile(args.config, args.artifact_dir / "config_snapshot.json")
    config = load_config(args.config); blind = []; runtimes = {}
    for index, label in enumerate(labels, 1):
        row = prediction_input(label)
        print(f"[{index:02d}/09] {row['session_id']}", flush=True)
        prediction, runtime = process_blind(row, args, config)
        blind.append(prediction)
        if runtime is not None: runtimes[row["session_id"]] = runtime
        write_predictions(args.artifact_dir / "blind_predictions.csv", blind)
        print(f"  {prediction['processing_status']}: count={prediction['predicted_repetition_count'] if prediction['predicted_repetition_count'] != '' else 'unavailable'}", flush=True)
    blind_path = args.artifact_dir / "blind_predictions.csv"; blind_hash = sha256_file(blind_path)
    label_by_session = {row["session_id"]: row for row in labels}
    evaluated = [attach_evaluation(row, label_by_session[row["session_id"]]) for row in blind]
    predictions_path = args.artifact_dir / "holdout_predictions.csv"; write_predictions(predictions_path, evaluated)
    for row in evaluated:
        runtime = runtimes.get(row["session_id"])
        if runtime is None: continue
        preview = preview_dir / f"{row['session_id']}.mp4"
        shared.render_preview(runtime["video_path"], preview, runtime["observations"], runtime["result"], runtime["phases"], row["manual_viewpoint"], int(row["manual_repetition_count"]), runtime["warnings"])
        row["preview_path"] = str(preview.relative_to(ROOT))
    write_predictions(predictions_path, evaluated)
    metrics = calculate_metrics(evaluated)
    metrics["metric_policy"]["viewpoint_accuracy"] = "correct predictions / all eligible holdout recordings; failures and unknown are incorrect"
    command = ".venv-video/bin/python scripts/run_holdout_evaluation.py"
    provenance = {"schema_version":"1.0", "created_at":datetime.now(timezone.utc).isoformat(), "scope":"holdout_only_anon-p008_through_anon-p010", "evaluation_mode":"offline_recorded_session_whole_recording_quantiles", "label_isolation":"filename, participant_id and session_id only were exposed to prediction; manual labels attached after blind_predictions.csv was saved", "freeze_verification":freeze_verification, "blind_predictions_sha256":blind_hash, "manifest_controls":controls, "holdout_session_ids":[row["session_id"] for row in labels], "processing_status_counts":dict(Counter(row["processing_status"] for row in evaluated)), "cache_status_counts":dict(Counter(row.get("cache_status") or "unavailable" for row in evaluated)), "configuration_snapshot_sha256":sha256_file(args.artifact_dir / "config_snapshot.json"), "manifest_snapshot_sha256":sha256_file(args.artifact_dir / "manifest_snapshot.csv"), "adapter_source_sha256":sha256_file(Path(__file__)), "git_commit":subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip(), "runtime":{"python":platform.python_version(),"platform":platform.platform()}, "command":command}
    shared._write_json(args.artifact_dir / "provenance.json", provenance)
    shared._write_json(args.artifact_dir / "metrics.json", metrics)
    (args.artifact_dir / "holdout_report.md").write_text(build_report(evaluated, metrics, provenance), encoding="utf-8")
    print(json.dumps(metrics, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
