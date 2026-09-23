#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "artifacts/real_recordings/development_baseline"
V2 = ROOT / "artifacts/real_recordings/development_baseline_v2"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def pct(value: float) -> str:
    return f"{value:.1%}"


def main() -> None:
    v1_metrics = json.loads((V1 / "metrics.json").read_text(encoding="utf-8"))
    v2_metrics = json.loads((V2 / "metrics.json").read_text(encoding="utf-8"))
    v1_rows = {row["session_id"]: row for row in read_csv(ROOT / "data/processed/development_recording_predictions.csv")}
    v2_rows = read_csv(V2 / "development_recording_predictions.csv")
    comparisons = []
    for row in v2_rows:
        old = v1_rows[row["session_id"]]
        manual = int(row["manual_repetition_count"])
        before = int(old["predicted_repetition_count"])
        after = int(row["predicted_repetition_count"])
        comparisons.append({
            "session_id": row["session_id"], "participant_id": row["participant_id"],
            "manual_viewpoint": row["manual_viewpoint"], "manual_count": manual,
            "baseline_count": before, "v2_count": after, "baseline_signed_error": before - manual,
            "v2_signed_error": after - manual, "absolute_error_change": abs(after - manual) - abs(before - manual),
            "regression": str(abs(after - manual) > abs(before - manual)).lower(),
        })
    write_csv(V2 / "baseline_comparison.csv", comparisons)

    reviews = [
        {"session_id":"anon-p004_pushup_side_take01","manual_count":3,"v2_count":4,"discrepant_interval_ms":"0-2967","classification":"complete_movement_cycle","visual_finding":"The first observed top-bottom-top movement is complete, but begins at the recording boundary and may be setup rather than an intended repetition.","ambiguity":"human_review_required","contact_sheet":"residual_review/anon-p004_pushup_side_take01-contact-sheet.jpg"},
        {"session_id":"anon-p005_pushup_oblique_take01","manual_count":6,"v2_count":5,"discrepant_interval_ms":"0-967","classification":"incomplete_boundary_movement","visual_finding":"Recording begins below the established top state; the participant rises to extension by about 0.967 s, so no preceding top-to-bottom transition is observable.","ambiguity":"boundary intent should be confirmed by human reviewer","contact_sheet":"residual_review/anon-p005_pushup_oblique_take01-contact-sheet.jpg"},
        {"session_id":"anon-p005_pushup_side_take01","manual_count":5,"v2_count":4,"discrepant_interval_ms":"0-933","classification":"incomplete_boundary_movement","visual_finding":"Recording begins during the bottom/rising portion and reaches extension near 0.933 s; the leading descent is outside the recording.","ambiguity":"boundary intent should be confirmed by human reviewer","contact_sheet":"residual_review/anon-p005_pushup_side_take01-contact-sheet.jpg"},
        {"session_id":"anon-p006_pushup_oblique_take01","manual_count":8,"v2_count":7,"discrepant_interval_ms":"7900-8700","classification":"incomplete_boundary_movement","visual_finding":"A terminal descent reaches the bottom near the end of the file but has no return to top before 8.700 s; the state machine correctly discards it as incomplete.","ambiguity":"manual protocol may count a terminal partial cycle; human review required","contact_sheet":"residual_review/anon-p006_pushup_oblique_take01-contact-sheet.jpg"},
        {"session_id":"anon-p007_pushup_side_take01","manual_count":4,"v2_count":3,"discrepant_interval_ms":"7867-9935","classification":"incomplete_boundary_movement","visual_finding":"After the third completed cycle, the participant descends again and remains low through the 9.935 s boundary without returning to top.","ambiguity":"manual protocol may count a terminal partial cycle; human review required","contact_sheet":"residual_review/anon-p007_pushup_side_take01-contact-sheet.jpg"},
    ]
    write_csv(V2 / "residual_error_review.csv", reviews)

    b = v1_metrics["repetition_count"]
    n = v2_metrics["repetition_count"]
    regressions = [row for row in comparisons if row["regression"] == "true"]
    provenance = json.loads((V2 / "provenance.json").read_text(encoding="utf-8"))
    freeze = {
        "schema_version": "1.0", "created_at": datetime.now(timezone.utc).isoformat(),
        "recommendation": "freeze_for_holdout_evaluation_after_human_acknowledgement_of_residual_boundary_ambiguities",
        "configuration_sha256": sha256(ROOT / "configs/video_processing.json"),
        "configuration_snapshot_sha256": sha256(V2 / "config_snapshot.json"),
        "manifest_sha256": sha256(ROOT / "data/incoming/recordings_manifest.csv"),
        "pose_model_sha256": sha256(ROOT / "models/pose_landmarker_full.task"),
        "git_commit": provenance.get("git_commit"), "source_hashes": provenance["source_hashes"],
        "reproduction_command": provenance["command"],
        "threshold_scope": "entire recording; offline recorded-session analysis",
        "holdout_access": "not opened or processed",
    }
    (V2 / "freeze_manifest.json").write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Development baseline v2 freeze verification", "", "## Outcome", "",
        "The combined phase-segmentation candidate reproduced exactly. It is suitable to freeze for the next holdout evaluation, subject to acknowledging the five residual disagreements and obtaining human review of the boundary ambiguities. No further threshold tuning was performed.", "",
        "Threshold estimation uses the 20th and 80th percentiles of the selected signal over the entire recording. The pipeline is therefore **offline recorded-session analysis**; this result does not establish equivalent real-time performance.", "",
        "## Before / after", "",
        "| Metric | Original baseline | Baseline v2 |", "|---|---:|---:|",
        f"| Coverage | {pct(b['coverage'])} | {pct(n['coverage'])} |",
        f"| MAE | {b['count_mae']:.3f} | {n['count_mae']:.3f} |",
        f"| RMSE | {b['count_rmse']:.3f} | {n['count_rmse']:.3f} |",
        f"| Median absolute error | {b['median_absolute_error']} | {n['median_absolute_error']} |",
        f"| Exact counts | {round(b['exact_count_accuracy']*21)}/21 | {round(n['exact_count_accuracy']*21)}/21 |",
        f"| Within ±1 | {round(b['within_one_accuracy']*21)}/21 | {round(n['within_one_accuracy']*21)}/21 |",
        f"| Mean signed error | {b['mean_signed_error']:.3f} | {n['mean_signed_error']:.3f} |",
        f"| Predicted/manual total | {b['total_predicted_answered']}/{b['total_manual_answered']} | {n['total_predicted_answered']}/{n['total_manual_answered']} |",
        f"| Assessment coverage | {pct(v1_metrics['reliability']['assessment_coverage'])} | {pct(v2_metrics['reliability']['assessment_coverage'])} |", "",
        "Count coverage is based on semantic availability: numeric zero is an answered prediction, while blank/`None` is unavailable. All 21 v2 counts were available; this is not inferred merely from the presence of a numeric field.", "",
        "Technique accuracy remains unavailable because there are no trainer technique labels.", "",
        "## Regression audit", "",
        f"There was one absolute-error regression: `{regressions[0]['session_id']}` changed from exact (3) to +1 (4). The other 20 recordings were unchanged or improved, and all 21 remain within ±1.", "",
        "## Residual visual review", "",
        "| Session | Discrepant interval | Classification | Finding |", "|---|---:|---|---|",
    ]
    for item in reviews:
        lines.append(f"| {item['session_id']} | {item['discrepant_interval_ms']} ms | {item['classification']} | {item['visual_finding']} {item['ambiguity']}. |")
    lines += ["", "Contact sheets are saved under `residual_review/`; review judgments do not change manual labels. No residual was classified as a state-machine double count or partial-range movement. The p004 first cycle is a complete visual cycle but its boundary/setup intent is ambiguous.", "",
        "## Freeze material", "", f"- Config SHA-256: `{freeze['configuration_sha256']}`", f"- Manifest SHA-256: `{freeze['manifest_sha256']}`", f"- Model SHA-256: `{freeze['pose_model_sha256']}`", f"- Git revision: `{freeze['git_commit']}`", "- Exact source hashes and reproduction command: `freeze_manifest.json` and `provenance.json`.", "", "## Unresolved issues", "", "- Five count disagreements remain; four are recording-boundary losses and one is a complete-cycle/setup ambiguity.", "- Whole-recording quantiles prevent an equivalent streaming/real-time claim.", "- Assessment coverage is 66.4%; unsupported viewpoint/quality cases remain explicit.", "- Technique accuracy cannot be measured without trainer labels.", "- Holdout performance is unknown; holdout recordings were not opened or processed.", ""]
    (V2 / "freeze_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
