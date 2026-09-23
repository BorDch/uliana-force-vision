#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
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

from uliana.config import load_config
from uliana.development_baseline import (
    PREDICTION_FIELDS,
    calculate_metrics,
    development_rows,
    error_rows,
    json_cell,
    select_demo_candidates,
    validate_manifest,
    write_predictions,
)
from uliana.reporting.provenance import StaleCacheError, build_provenance, sha256_file, verify_cache
from uliana.video.camera_session import analyze_camera_observations, write_camera_outputs
from uliana.video.pose_estimator import MediaPipeObservationAdapter
from uliana.video.processing import observation_from_dict, process_observations, write_observations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the frozen development-only real-video baseline.")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/incoming/recordings_manifest.csv")
    parser.add_argument("--video-root", type=Path, default=ROOT / "data/incoming/recordings")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/video_processing.json")
    parser.add_argument("--model", type=Path, default=ROOT / "models/pose_landmarker_full.task")
    parser.add_argument("--predictions", type=Path, default=ROOT / "data/processed/development_recording_predictions.csv")
    parser.add_argument("--artifact-dir", type=Path, default=ROOT / "artifacts/real_recordings/development_baseline")
    parser.add_argument("--preview-dir", type=Path, default=ROOT / "data/review/previews/development")
    parser.add_argument("--pose-cache-root", type=Path, help="Validated landmark cache to reuse without rewriting it.")
    parser.add_argument("--force-inference", action="store_true", help="Ignore otherwise valid cached landmarks.")
    return parser.parse_args()


def _read_observations(path: Path):
    return [
        observation_from_dict(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _load_or_infer_raw(row: dict[str, str], video_path: Path, args: argparse.Namespace):
    cache_dir = args.artifact_dir / "cache" / row["session_id"]
    raw_path = cache_dir / "raw_video_observations.jsonl"
    cache_manifest = cache_dir / "cache_provenance.json"
    cache_inputs = {"source_video": video_path}
    cache_configs = {"video_processing": args.config}
    if raw_path.is_file() and cache_manifest.is_file() and not args.force_inference:
        try:
            verify_cache(cache_manifest, inputs=cache_inputs, configs=cache_configs, model=args.model)
            observations = _read_observations(raw_path)
            if observations and all(item.session_id == row["session_id"] for item in observations):
                return observations, cache_dir, "hit"
        except (StaleCacheError, OSError, ValueError, KeyError, json.JSONDecodeError):
            pass
    if args.pose_cache_root is not None and not args.force_inference:
        external_dir = args.pose_cache_root / row["session_id"]
        external_raw = external_dir / "raw_video_observations.jsonl"
        external_manifest = external_dir / "cache_provenance.json"
        if external_raw.is_file() and external_manifest.is_file():
            cached = json.loads(external_manifest.read_text(encoding="utf-8"))
            expected_video = sha256_file(video_path)
            expected_model = sha256_file(args.model)
            if cached.get("input_hashes", {}).get("source_video") != expected_video:
                raise StaleCacheError(f"external pose cache source mismatch: {row['session_id']}")
            if cached.get("model_hash") != expected_model:
                raise StaleCacheError(f"external pose cache model mismatch: {row['session_id']}")
            observations = _read_observations(external_raw)
            if not observations or not all(item.session_id == row["session_id"] for item in observations):
                raise StaleCacheError(f"external pose cache session mismatch: {row['session_id']}")
            cache_dir.mkdir(parents=True, exist_ok=True)
            _write_json(cache_dir / "pose_cache_reference.json", {
                "source_cache": str(external_dir.relative_to(ROOT)),
                "source_video_sha256": expected_video,
                "pose_model_sha256": expected_model,
                "validation": "source video, pose model and session_id matched; phase segmentation recomputed",
            })
            return observations, cache_dir, "reused_external"
    observations = [
        observation
        for observation, _image in MediaPipeObservationAdapter(args.model).process(video_path, row["session_id"])
    ]
    if not observations:
        raise RuntimeError("video yielded no observations")
    cache_dir.mkdir(parents=True, exist_ok=True)
    write_observations(raw_path, observations)
    provenance = build_provenance(
        inputs=cache_inputs,
        configs=cache_configs,
        model=args.model,
        calibration_id=None,
        synchronization_method=None,
        data_declaration="real_camera_only_development_landmark_cache",
    )
    _write_json(cache_manifest, provenance)
    return observations, cache_dir, "miss"


def _fit_dimensions(width: int, height: int, max_width: int = 1280, max_height: int = 720) -> tuple[int, int]:
    scale = min(1.0, max_width / width, max_height / height)
    output_width = max(2, int(math.floor(width * scale / 2) * 2))
    output_height = max(2, int(math.floor(height * scale / 2) * 2))
    return output_width, output_height


def render_preview(
    video_path: Path,
    destination: Path,
    observations,
    result,
    phases: dict[int, str],
    manual_viewpoint: str,
    manual_count: int,
    warnings: list[str],
) -> None:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("video extras are required") from exc
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"cannot open video: {video_path}")
    source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 30.0
    width, height = _fit_dimensions(source_width, source_height)
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(f"cannot create preview: {destination}")
    connections = (
        ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
        ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
        ("left_shoulder", "right_shoulder"), ("left_hip", "right_hip"),
        ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
        ("left_hip", "left_ankle"), ("right_hip", "right_ankle"),
    )
    predicted_count = result.repetition_count if result.repetition_count is not None else "unavailable"
    predicted_viewpoint = result.detected_viewpoint.value
    viewpoint_confidence = result.detected_viewpoint.confidence
    signal = result.provenance.get("phase_signal") or "unavailable"
    warning_text = ", ".join(warnings[:2]) if warnings else "none"
    try:
        for index, observation in enumerate(observations):
            ok, image = capture.read()
            if not ok:
                break
            if index >= len(observations):
                break
            if (source_width, source_height) != (width, height):
                image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
            landmarks = observation.pose.landmarks
            for first, second in connections:
                if first in landmarks and second in landmarks:
                    a, b = landmarks[first], landmarks[second]
                    cv2.line(
                        image,
                        (round(a.x * width), round(a.y * height)),
                        (round(b.x * width), round(b.y * height)),
                        (80, 220, 160),
                        2,
                    )
            phase = phases.get(observation.timestamp_ms, "unknown")
            frame_warning = observation.quality_flags[0] if observation.quality_flags else warning_text
            lines = [
                f"Session: {result.session_id}",
                f"Viewpoint manual={manual_viewpoint} predicted={predicted_viewpoint} confidence={viewpoint_confidence:.2f}" if viewpoint_confidence is not None else f"Viewpoint manual={manual_viewpoint} predicted={predicted_viewpoint} confidence=unavailable",
                f"Repetitions manual={manual_count} detected={predicted_count}",
                f"Phase signal={signal} current={phase}",
                f"Warnings: {frame_warning}",
            ]
            overlay = image.copy()
            cv2.rectangle(overlay, (8, 8), (min(width - 8, 1000), 158), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.55, image, 0.45, 0, image)
            for line_number, text in enumerate(lines):
                color = (80, 80, 255) if line_number == 4 and frame_warning != "none" else (235, 235, 235)
                cv2.putText(image, text, (18, 32 + line_number * 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
            cv2.putText(
                image,
                "CAMERA PROXY — NOT MEDICAL/3D/360".replace("—", "-"),
                (18, height - 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (50, 190, 255),
                2,
            )
            writer.write(image)
    finally:
        capture.release()
        writer.release()


def _base_prediction(row: dict[str, str]) -> dict:
    return {
        "filename": row["filename"],
        "participant_id": row["participant_id"],
        "session_id": row["session_id"],
        "manual_viewpoint": row["manual_viewpoint"],
        "manual_repetition_count": row["manual_repetition_count"],
        **{name: "" for name in PREDICTION_FIELDS if name not in row},
    }


def process_recording(row: dict[str, str], args: argparse.Namespace, config: dict) -> dict:
    started = time.perf_counter()
    prediction = _base_prediction(row)
    video_path = args.video_root / row["filename"]
    try:
        raw, cache_dir, cache_status = _load_or_infer_raw(row, video_path, args)
        observations, video_summary = process_observations(raw, config)
        result, features, phases, camera_metrics = analyze_camera_observations(observations, video_summary, config)
        write_observations(cache_dir / "video_observations.jsonl", observations)
        _write_json(cache_dir / "video_summary.json", video_summary)
        write_camera_outputs(cache_dir, result, features, camera_metrics)
        unavailable = [
            {"condition": item.condition, "rep_id": item.rep_id, "reason": item.reason}
            for item in result.unavailable_assessments
        ]
        reasons = sorted({item["reason"] for item in unavailable if item["reason"]})
        warnings = list(dict.fromkeys(
            result.warnings
            + list(video_summary.get("warnings", []))
            + sorted(video_summary.get("quality_code_counts", {}))
        ))
        preview_path = args.preview_dir / f"{row['session_id']}.mp4"
        render_preview(
            video_path,
            preview_path,
            observations,
            result,
            phases,
            row["manual_viewpoint"],
            int(row["manual_repetition_count"]),
            warnings,
        )
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
            "processing_status": "success",
            "cache_status": cache_status,
            "preview_path": str(preview_path.relative_to(ROOT)),
            "error_message": "",
        })
    except Exception as exc:
        prediction.update({
            "processing_status": "failed",
            "unavailable_assessments": "[]",
            "unavailable_reasons": "processing_failed",
            "quality_warnings": f"processing_failed:{type(exc).__name__}",
            "error_message": f"{type(exc).__name__}: {exc}",
        })
    prediction["processing_time_seconds"] = round(time.perf_counter() - started, 3)
    return prediction


def _fmt(value, percentage: bool = False) -> str:
    if value is None:
        return "unavailable"
    if percentage:
        return f"{value:.1%}"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _count_table(grouped: dict[str, dict], label: str) -> str:
    lines = [f"| {label} | Eligible | Unavailable | Coverage | MAE | RMSE | Median AE | Exact | Within ±1 | Mean signed error | Predicted/manual answered |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, metric in grouped.items():
        lines.append(
            f"| {name} | {metric['eligible_recordings']} | {metric['unavailable_predictions']} | {_fmt(metric['coverage'], True)} | "
            f"{_fmt(metric['count_mae'])} | {_fmt(metric['count_rmse'])} | {_fmt(metric['median_absolute_error'])} | "
            f"{_fmt(metric['exact_count_accuracy'], True)} | {_fmt(metric['within_one_accuracy'], True)} | "
            f"{_fmt(metric['mean_signed_error'])} | {metric['total_predicted_answered']}/{metric['total_manual_answered']} |"
        )
    return "\n".join(lines)


def build_report(rows: list[dict], metrics: dict, demos: list[dict], provenance: dict) -> str:
    repetition = metrics["repetition_count"]
    viewpoint = metrics["viewpoint"]
    reliability = metrics["reliability"]
    errors = error_rows(rows)
    lines = [
        "# Development real-video baseline",
        "",
        "## Dataset composition",
        "",
        "This baseline contains 21 recordings and 116 manually counted repetitions from development participants anon-p001–anon-p007. Each participant contributes front, oblique and side recordings. Holdout participants anon-p008–anon-p010 were validated at the manifest level only and were not opened, processed, previewed or used for tuning.",
        "",
        "The manual condition `natural_form_unlabelled` is an acquisition label. It is not a trainer-labelled technique judgment and is not treated as correct technique.",
        "",
        "## Configuration and provenance",
        "",
        f"- Manifest SHA-256: `{provenance['manifest_sha256']}`",
        f"- Video-processing configuration SHA-256: `{provenance['video_processing_config_sha256']}`",
        f"- Pose model SHA-256: `{provenance['pose_model_sha256']}`",
        f"- Git revision: `{provenance.get('git_commit') or 'unavailable'}`",
        "- Configuration was snapshotted without modification before processing.",
        "- Reused landmark caches were accepted only when source-video hash, pose-model hash and session ID matched. Phase segmentation, counts and assessments were recomputed with this snapshot.",
        "- Threshold quantiles are estimated from the entire recording. This is offline recorded-session analysis; equivalent real-time performance is not claimed.",
        "",
        "## Metric definitions",
        "",
        "Repetition error is predicted count minus manual count. MAE, RMSE, median absolute error, exact accuracy, within-one accuracy and mean signed error use answered predictions only. Unavailable predictions reduce coverage and are never converted to zero. Viewpoint accuracy uses every eligible development recording; unknown and processing failures are incorrect. Assessment coverage is answered assessments divided by eligible assessments.",
        "",
        "## Overall results",
        "",
        f"- Repetition-count coverage: {_fmt(repetition['coverage'], True)} ({repetition['answered_recordings']}/{repetition['eligible_recordings']}); unavailable: {repetition['unavailable_predictions']}",
        f"- Count MAE: {_fmt(repetition['count_mae'])}; RMSE: {_fmt(repetition['count_rmse'])}; median absolute error: {_fmt(repetition['median_absolute_error'])}",
        f"- Exact-count accuracy: {_fmt(repetition['exact_count_accuracy'], True)}; within ±1: {_fmt(repetition['within_one_accuracy'], True)}",
        f"- Mean signed error: {_fmt(repetition['mean_signed_error'])}",
        f"- Total predicted/manual repetitions among answered cases: {repetition['total_predicted_answered']}/{repetition['total_manual_answered']} (manual total across all eligible recordings: {repetition['total_manual_eligible']})",
        f"- Viewpoint accuracy: {_fmt(viewpoint['overall_accuracy'], True)}; unknown rate: {_fmt(viewpoint['unknown_rate'], True)}",
        f"- Mean viewpoint confidence, correct/incorrect: {_fmt(viewpoint['mean_confidence_correct'])}/{_fmt(viewpoint['mean_confidence_incorrect'])}",
        f"- Processing success rate: {_fmt(reliability['processing_success_rate'], True)}",
        f"- Mean pose-detection coverage: {_fmt(reliability['mean_pose_detection_coverage'], True)}",
        f"- Phase-signal availability: {_fmt(reliability['phase_signal_availability'], True)}",
        f"- Assessment coverage: {_fmt(reliability['assessment_coverage'], True)}",
        "",
        "## Results by viewpoint",
        "",
        _count_table(metrics["repetition_count_by_viewpoint"], "Manual viewpoint"),
        "",
        "Viewpoint classification accuracy by class: " + ", ".join(f"{name}={_fmt(value, True)}" for name, value in viewpoint["accuracy_by_viewpoint"].items()) + ".",
        "",
        "## Results by participant",
        "",
        _count_table(metrics["repetition_count_by_participant"], "Participant"),
        "",
        "## Viewpoint confusion matrix",
        "",
        "| Actual \\ Predicted | front | oblique | side | unknown |",
        "|---|---:|---:|---:|---:|",
    ]
    for actual in ("front", "oblique", "side"):
        values = viewpoint["confusion_matrix"][actual]
        lines.append(f"| {actual} | {values['front']} | {values['oblique']} | {values['side']} | {values['unknown']} |")
    lines += [
        "",
        "## Per-recording repetition errors",
        "",
        "Sorted by absolute error, with unavailable predictions last.",
        "",
        "| Session | Participant | Manual view | Predicted view | Manual | Predicted | Signed error | Absolute error | Confidence | Pose coverage | Phase signal | Warnings | Status |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in errors:
        lines.append(
            f"| {row['session_id']} | {row['participant_id']} | {row['manual_viewpoint']} | {row['predicted_viewpoint']} | "
            f"{row['manual_repetition_count']} | {_fmt(row['predicted_repetition_count'])} | {_fmt(row['signed_error'])} | {_fmt(row['absolute_error'])} | "
            f"{_fmt(row['prediction_confidence'])} | {_fmt(row['pose_coverage'], True)} | {row['phase_signal']} | {row['warnings'] or 'none'} | {row['status']} |"
        )
    lines += [
        "",
        "## Unavailable cases and reasons",
        "",
    ]
    unavailable_predictions = [row for row in rows if row.get("predicted_repetition_count") in (None, "")]
    if unavailable_predictions:
        lines.extend(f"- `{row['session_id']}`: {row.get('error_message') or row.get('unavailable_reasons') or 'phase signal unavailable'}" for row in unavailable_predictions)
    else:
        lines.append("No repetition-count prediction was unavailable.")
    lines += [
        "",
        "Unavailable assessment reasons: " + (", ".join(f"{name}={count}" for name, count in reliability["unavailable_reason_frequencies"].items()) or "none") + ".",
        "",
        "Quality-warning frequencies: " + (", ".join(f"{name}={count}" for name, count in reliability["quality_warning_frequencies"].items()) or "none") + ".",
        "",
        "## Observed limitations",
        "",
        "- This is a small participant-wise development evaluation, not a holdout result.",
        "- Monocular MediaPipe landmarks are camera proxies, not validated 3D motion capture.",
        "- Viewpoint and phase thresholds are experimental and remain frozen for this run.",
        "- Repetition labels do not support technique-accuracy measurement.",
        "- Assessment availability varies by viewpoint and evidence quality; unavailable outputs are retained explicitly.",
        "",
        "## Three strongest demo candidates",
        "",
        "Candidates require a rendered overlay, an available phase signal and count, pose coverage at or above the configured 70% gate, count confidence at or above the configured 0.55 signal gate, then rank by absolute count error, pose coverage and count confidence. Selection includes a side recording and a front or oblique recording when eligible.",
        "",
    ]
    if demos:
        lines += [
            "| Session | Manual view | Count manual/predicted | Absolute error | Pose coverage | Count confidence | Preview |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
        for row in demos:
            lines.append(
                f"| {row['session_id']} | {row['manual_viewpoint']} | {row['manual_repetition_count']}/{row['predicted_repetition_count']} | "
                f"{row['absolute_error']} | {_fmt(float(row['pose_detection_coverage']), True)} | {_fmt(float(row['repetition_confidence']))} | `{row['preview_path']}` |"
            )
    else:
        lines.append("No recording met all transparent demo-selection gates.")
    lines += [
        "",
        "## Exact commands for reproduction",
        "",
        "```bash",
        ".venv-video/bin/python scripts/run_development_baseline.py",
        ".venv-video/bin/python -m pytest -q tests/test_development_baseline.py tests/test_camera_milestone4.py",
        ".venv-video/bin/python -m pytest -q",
        ".venv-video/bin/python -m compileall -q scripts src tests",
        "```",
        "",
        "Do not evaluate holdout recordings until configuration is explicitly frozen after reviewing this development report.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    for name in ("manifest", "video_root", "config", "model", "predictions", "artifact_dir", "preview_dir", "pose_cache_root"):
        value = getattr(args, name)
        if value is not None and not value.is_absolute():
            setattr(args, name, ROOT / value)
    rows, controls = validate_manifest(args.manifest, args.video_root)
    selected = development_rows(rows)
    if len(selected) != 21:
        raise RuntimeError(f"development selection yielded {len(selected)} rows, expected 21")
    if not args.model.is_file():
        raise FileNotFoundError(f"pose model not found: {args.model}")
    config = load_config(args.config)
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    args.preview_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.manifest, args.artifact_dir / "manifest_snapshot.csv")
    shutil.copyfile(args.config, args.artifact_dir / "config_snapshot.json")

    predictions = []
    for index, row in enumerate(selected, 1):
        print(f"[{index:02d}/{len(selected)}] {row['session_id']}", flush=True)
        prediction = process_recording(row, args, config)
        predictions.append(prediction)
        state = prediction["processing_status"]
        count = prediction["predicted_repetition_count"] if prediction["predicted_repetition_count"] != "" else "unavailable"
        print(f"  {state}: count={count}, cache={prediction.get('cache_status') or 'n/a'}", flush=True)
        write_predictions(args.predictions, predictions)

    write_predictions(args.predictions, predictions)
    metrics = calculate_metrics(predictions)
    demos = select_demo_candidates(
        predictions,
        config["phase_segmentation"]["minimum_valid_frame_fraction"],
        config["phase_segmentation"]["minimum_signal_confidence"],
    )
    provenance = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "development_only_anon-p001_through_anon-p007",
        "holdout_policy": "manifest existence/count validation only; video content not opened or processed",
        "manifest_path": str(args.manifest.relative_to(ROOT)),
        "manifest_sha256": sha256_file(args.manifest),
        "manifest_snapshot_sha256": sha256_file(args.artifact_dir / "manifest_snapshot.csv"),
        "video_processing_config_path": str(args.config.relative_to(ROOT)),
        "video_processing_config_sha256": sha256_file(args.config),
        "config_snapshot_sha256": sha256_file(args.artifact_dir / "config_snapshot.json"),
        "pose_model_path": str(args.model.relative_to(ROOT)),
        "pose_model_sha256": sha256_file(args.model),
        "git_commit": _git_commit(),
        "source_hashes": {
            str(path.relative_to(ROOT)): sha256_file(path)
            for path in (
                ROOT / "src/uliana/video/phases.py",
                ROOT / "src/uliana/video/camera_session.py",
                ROOT / "src/uliana/development_baseline.py",
                ROOT / "scripts/run_development_baseline.py",
            )
        },
        "runtime": {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine()},
        "manifest_controls": controls,
        "development_session_ids": [row["session_id"] for row in selected],
        "processing_status_counts": dict(Counter(row["processing_status"] for row in predictions)),
        "cache_status_counts": dict(Counter(row.get("cache_status") or "unavailable" for row in predictions)),
        "command": ".venv-video/bin/python scripts/run_development_baseline.py --artifact-dir artifacts/real_recordings/development_baseline_v2 --predictions artifacts/real_recordings/development_baseline_v2/development_recording_predictions.csv --preview-dir artifacts/real_recordings/development_baseline_v2/previews --pose-cache-root artifacts/real_recordings/development_baseline/cache",
    }
    _write_json(args.artifact_dir / "provenance.json", provenance)
    _write_json(args.artifact_dir / "metrics.json", metrics)
    report = build_report(predictions, metrics, demos, provenance)
    (args.artifact_dir / "development_baseline_report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"metrics": metrics, "demo_candidates": [row["session_id"] for row in demos]}, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
