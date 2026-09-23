#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uliana.video_evaluation import match_events


def optional_float(value: str) -> float | None:
    try: return float(value) if value.strip() else None
    except ValueError: return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate cached real-video results only where manual references exist.")
    parser.add_argument("--manifest", required=True, type=Path); parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--results-root", type=Path, default=ROOT / "artifacts" / "real_video")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "real_video" / "evaluation")
    parser.add_argument("--tolerance-seconds", type=float, default=.5)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    manifest = {row["video_id"]: row for row in csv.DictReader(args.manifest.open(encoding="utf-8"))}
    annotations = defaultdict(list)
    for row in csv.DictReader(args.annotations.open(encoding="utf-8")): annotations[row["video_id"]].append(row)
    clips = []
    unknown_participants = []
    for video_id, meta in manifest.items():
        if not meta.get("participant_id") or meta["participant_id"] == "unknown": unknown_participants.append(video_id)
        summary_path, reps_path = args.results_root / video_id / "summary.json", args.results_root / video_id / "repetitions.json"
        refs = [row for row in annotations[video_id] if optional_float(row.get("bottom_seconds", "")) is not None]
        if not summary_path.exists() or not reps_path.exists() or not refs: continue
        summary = json.loads(summary_path.read_text()); detections = json.loads(reps_path.read_text())
        provenance_path = args.results_root / video_id / "provenance.json"
        provenance = json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
        reference_times = [optional_float(row["bottom_seconds"]) for row in refs]
        detected_times = [row["bottom_ms"] / 1000 for row in detections if row.get("bottom_ms") is not None]
        matches = match_events(reference_times, detected_times, args.tolerance_seconds)
        cue_compared = cue_agreed = 0
        for match in matches:
            annotation, detection = refs[match.annotation_index], detections[match.detection_index]
            expected = None
            if annotation.get("depth_label") == "insufficient": expected = "Increase movement depth."
            elif annotation.get("body_line_label") == "error": expected = "Keep your body straight."
            elif annotation.get("depth_label") == "adequate" and annotation.get("body_line_label") == "good": expected = "Good repetition."
            if expected is not None: cue_compared += 1; cue_agreed += detection["cue"] == expected
        clips.append({"video_id": video_id, "participant_id": meta.get("participant_id"), "camera_view": meta.get("camera_view"),
            "split": meta.get("split"), "annotated_count": len(refs), "detected_count": len(detections),
            "absolute_count_error": abs(len(refs) - len(detections)), "event_precision": len(matches) / len(detections) if detections else None,
            "event_recall": len(matches) / len(refs) if refs else None,
            "mean_boundary_error_seconds": sum(x.timing_error_seconds for x in matches) / len(matches) if matches else None,
            "required_landmark_availability": summary.get("required_landmark_availability"),
            "decision_coverage": summary.get("decision_coverage"),
            "mean_inference_ms_per_frame_excluding_warmup": summary.get("mean_inference_ms_per_frame_excluding_warmup"),
            "runtime_hardware_context": provenance.get("runtime"),
            "cue_agreement": cue_agreed / cue_compared if cue_compared else None, "cue_agreement_denominator": cue_compared})
    result = {"metric_definitions": {"event_matching": f"closest greedy one-to-one bottom-event match within {args.tolerance_seconds}s",
        "precision": "matched detections / detections", "recall": "matched annotations / annotations",
        "cue_agreement": "matching cues / matched repetitions with known assessable manual technique labels"},
        "clips": clips, "strict_participant_separation_established": not unknown_participants,
        "unknown_participant_video_ids": unknown_participants,
        "status": "evaluated_available_references" if clips else "unavailable_no_processed_clips_with_timed_manual_annotations"}
    (args.output / "metrics.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    report = "# Real-video evaluation\n\n" + ("No processed clip with timed manual annotations was available; metrics are unavailable, not zero.\n" if not clips else f"Evaluated {len(clips)} clips. See `metrics.json` for per-view and per-participant fields.\n")
    if unknown_participants: report += "\nStrict participant separation cannot be established for: " + ", ".join(unknown_participants) + ".\n"
    report += "\nThresholds must be frozen on development participants before interpreting test results. Pose visibility is reported as availability, not accuracy.\n"
    (args.output / "report.md").write_text(report, encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
