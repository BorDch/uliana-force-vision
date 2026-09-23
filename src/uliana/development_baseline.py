from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


MANIFEST_HEADER = [
    "filename",
    "participant_id",
    "session_id",
    "manual_viewpoint",
    "manual_repetition_count",
    "exercise_variation",
    "intended_condition",
    "consent_status",
    "split",
    "notes",
]

EXPECTED_CONTROLS = {
    "total_recordings": 30,
    "total_participants": 10,
    "development_recordings": 21,
    "development_repetitions": 116,
    "holdout_recordings": 9,
    "holdout_repetitions": 51,
    "total_repetitions": 167,
    "front_recordings": 10,
    "front_repetitions": 57,
    "oblique_recordings": 10,
    "oblique_repetitions": 54,
    "side_recordings": 10,
    "side_repetitions": 56,
}

PREDICTION_FIELDS = [
    "filename",
    "participant_id",
    "session_id",
    "manual_viewpoint",
    "manual_repetition_count",
    "predicted_viewpoint",
    "viewpoint_confidence",
    "predicted_repetition_count",
    "repetition_confidence",
    "selected_phase_signal",
    "pose_detection_coverage",
    "phase_signal_coverage",
    "assessment_coverage",
    "eligible_assessments",
    "answered_assessments",
    "unavailable_assessments",
    "unavailable_reasons",
    "quality_warnings",
    "processing_status",
    "processing_time_seconds",
    "cache_status",
    "preview_path",
    "error_message",
]


class ManifestValidationError(ValueError):
    pass


def validate_manifest(manifest_path: Path, video_root: Path) -> tuple[list[dict[str, str]], dict[str, int]]:
    raw = manifest_path.read_text(encoding="utf-8")
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        header = reader.fieldnames
    errors: list[str] = []
    if header != MANIFEST_HEADER:
        errors.append(f"header must be exactly {','.join(MANIFEST_HEADER)}")
    if "\\" in raw:
        errors.append("literal backslash/Markdown escaping found")
    if len(rows) != EXPECTED_CONTROLS["total_recordings"]:
        errors.append(f"total recordings is {len(rows)}, expected 30")
    filenames = [row.get("filename", "") for row in rows]
    sessions = [row.get("session_id", "") for row in rows]
    if len(set(filenames)) != len(filenames):
        errors.append("filenames are not unique")
    if len(set(sessions)) != len(sessions):
        errors.append("session IDs are not unique")
    missing = [name for name in filenames if not (video_root / name).is_file()]
    if missing:
        errors.append("referenced videos missing: " + ", ".join(missing))

    parsed_counts: dict[str, int] = {}
    for row in rows:
        value = row.get("manual_repetition_count", "")
        if not value.isdigit() or int(value) < 1:
            errors.append(f"invalid manual repetition count for {row.get('session_id', '<unknown>')}: {value!r}")
        else:
            parsed_counts[row["session_id"]] = int(value)
        if row.get("manual_viewpoint") not in {"front", "oblique", "side"}:
            errors.append(f"invalid manual viewpoint for {row.get('session_id', '<unknown>')}")
        if row.get("exercise_variation") != "standard_push_up":
            errors.append(f"unexpected exercise variation for {row.get('session_id', '<unknown>')}")
        if row.get("intended_condition") != "natural_form_unlabelled":
            errors.append(f"unexpected intended condition for {row.get('session_id', '<unknown>')}")
        if row.get("consent_status") != "granted":
            errors.append(f"consent not granted for {row.get('session_id', '<unknown>')}")

    participants: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        participants[row.get("participant_id", "")].append(row)
    if len(participants) != EXPECTED_CONTROLS["total_participants"]:
        errors.append(f"participant count is {len(participants)}, expected 10")
    for participant, participant_rows in participants.items():
        viewpoints = Counter(row.get("manual_viewpoint") for row in participant_rows)
        if viewpoints != Counter({"front": 1, "oblique": 1, "side": 1}):
            errors.append(f"{participant} does not have exactly one front, oblique and side recording")
        splits = {row.get("split") for row in participant_rows}
        if len(splits) != 1:
            errors.append(f"{participant} occurs in multiple splits: {sorted(splits)}")
        if participant.startswith("anon-p") and participant[-3:].isdigit():
            number = int(participant[-3:])
            expected_split = "development" if number <= 7 else "holdout"
            if splits != {expected_split}:
                errors.append(f"{participant} must be {expected_split}")

    def repetition_total(*, split: str | None = None, viewpoint: str | None = None) -> int:
        return sum(
            parsed_counts.get(row.get("session_id", ""), 0)
            for row in rows
            if (split is None or row.get("split") == split)
            and (viewpoint is None or row.get("manual_viewpoint") == viewpoint)
        )

    controls = {
        "total_recordings": len(rows),
        "total_participants": len(participants),
        "development_recordings": sum(row.get("split") == "development" for row in rows),
        "development_repetitions": repetition_total(split="development"),
        "holdout_recordings": sum(row.get("split") == "holdout" for row in rows),
        "holdout_repetitions": repetition_total(split="holdout"),
        "total_repetitions": repetition_total(),
        "front_recordings": sum(row.get("manual_viewpoint") == "front" for row in rows),
        "front_repetitions": repetition_total(viewpoint="front"),
        "oblique_recordings": sum(row.get("manual_viewpoint") == "oblique" for row in rows),
        "oblique_repetitions": repetition_total(viewpoint="oblique"),
        "side_recordings": sum(row.get("manual_viewpoint") == "side" for row in rows),
        "side_repetitions": repetition_total(viewpoint="side"),
    }
    for name, expected in EXPECTED_CONTROLS.items():
        if controls[name] != expected:
            errors.append(f"{name} is {controls[name]}, expected {expected}")
    if errors:
        raise ManifestValidationError("; ".join(errors))
    return rows, controls


def development_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    selected = [dict(row) for row in rows if row.get("split") == "development"]
    if any(row.get("participant_id", "") >= "anon-p008" for row in selected):
        raise ManifestValidationError("holdout participant selected for development processing")
    return selected


def write_predictions(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PREDICTION_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _optional_int(value) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_float(value) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def count_metrics(rows: list[dict]) -> dict:
    answered = [row for row in rows if _optional_int(row.get("predicted_repetition_count")) is not None]
    errors = [
        _optional_int(row["predicted_repetition_count"]) - int(row["manual_repetition_count"])
        for row in answered
    ]
    absolute = [abs(value) for value in errors]
    return {
        "eligible_recordings": len(rows),
        "answered_recordings": len(answered),
        "unavailable_predictions": len(rows) - len(answered),
        "coverage": len(answered) / len(rows) if rows else 0.0,
        "count_mae": sum(absolute) / len(absolute) if absolute else None,
        "count_rmse": math.sqrt(sum(value * value for value in errors) / len(errors)) if errors else None,
        "median_absolute_error": statistics.median(absolute) if absolute else None,
        "exact_count_accuracy": sum(value == 0 for value in errors) / len(errors) if errors else None,
        "within_one_accuracy": sum(abs(value) <= 1 for value in errors) / len(errors) if errors else None,
        "mean_signed_error": sum(errors) / len(errors) if errors else None,
        "total_predicted_answered": sum(_optional_int(row["predicted_repetition_count"]) or 0 for row in answered),
        "total_manual_answered": sum(int(row["manual_repetition_count"]) for row in answered),
        "total_manual_eligible": sum(int(row["manual_repetition_count"]) for row in rows),
    }


def grouped_count_metrics(rows: list[dict], key: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    return {name: count_metrics(groups[name]) for name in sorted(groups)}


def viewpoint_metrics(rows: list[dict]) -> dict:
    eligible = [row for row in rows if row.get("processing_status") == "success"]
    predictions = [row.get("predicted_viewpoint") or "unknown" for row in eligible]
    classes = ("front", "oblique", "side")
    matrix = {
        actual: {predicted: 0 for predicted in (*classes, "unknown")}
        for actual in classes
    }
    for row, predicted in zip(eligible, predictions):
        if predicted not in matrix[row["manual_viewpoint"]]:
            predicted = "unknown"
        matrix[row["manual_viewpoint"]][predicted] += 1
    correct_confidences = [
        _optional_float(row.get("viewpoint_confidence"))
        for row in eligible
        if row.get("predicted_viewpoint") == row.get("manual_viewpoint")
        and _optional_float(row.get("viewpoint_confidence")) is not None
    ]
    incorrect_confidences = [
        _optional_float(row.get("viewpoint_confidence"))
        for row in eligible
        if row.get("predicted_viewpoint") != row.get("manual_viewpoint")
        and _optional_float(row.get("viewpoint_confidence")) is not None
    ]
    return {
        "eligible_recordings": len(rows),
        "processed_recordings": len(eligible),
        "overall_accuracy": sum(row.get("predicted_viewpoint") == row.get("manual_viewpoint") for row in eligible) / len(rows) if rows else 0.0,
        "accuracy_by_viewpoint": {
            label: matrix[label][label] / sum(matrix[label].values()) if sum(matrix[label].values()) else None
            for label in classes
        },
        "unknown_rate": sum(value == "unknown" for value in predictions) / len(rows) if rows else 0.0,
        "mean_confidence_correct": sum(correct_confidences) / len(correct_confidences) if correct_confidences else None,
        "mean_confidence_incorrect": sum(incorrect_confidences) / len(incorrect_confidences) if incorrect_confidences else None,
        "confusion_matrix": matrix,
    }


def reliability_metrics(rows: list[dict]) -> dict:
    successful = [row for row in rows if row.get("processing_status") == "success"]
    pose = [_optional_float(row.get("pose_detection_coverage")) for row in successful]
    pose = [value for value in pose if value is not None]
    unavailable_reasons = Counter()
    warnings = Counter()
    total_eligible_assessments = total_answered_assessments = 0
    for row in rows:
        unavailable_reasons.update(filter(None, str(row.get("unavailable_reasons", "")).split("|")))
        warnings.update(filter(None, str(row.get("quality_warnings", "")).split("|")))
        total_eligible_assessments += int(row.get("eligible_assessments") or 0)
        total_answered_assessments += int(row.get("answered_assessments") or 0)
    return {
        "processing_success_rate": len(successful) / len(rows) if rows else 0.0,
        "mean_pose_detection_coverage": sum(pose) / len(pose) if pose else None,
        "phase_signal_availability": sum(bool(row.get("selected_phase_signal")) for row in successful) / len(rows) if rows else 0.0,
        "assessment_coverage": total_answered_assessments / total_eligible_assessments if total_eligible_assessments else 0.0,
        "unavailable_reason_frequencies": dict(sorted(unavailable_reasons.items())),
        "quality_warning_frequencies": dict(sorted(warnings.items())),
    }


def calculate_metrics(rows: list[dict]) -> dict:
    return {
        "metric_policy": {
            "count_metrics": "answered predictions only",
            "coverage": "answered repetition-count predictions / eligible recordings",
            "unavailable_predictions": "count against coverage and are not converted to zero",
            "signed_error": "predicted minus manual",
            "viewpoint_accuracy": "correct predictions / all eligible development recordings; failures and unknown are incorrect",
        },
        "repetition_count": count_metrics(rows),
        "repetition_count_by_viewpoint": grouped_count_metrics(rows, "manual_viewpoint"),
        "repetition_count_by_participant": grouped_count_metrics(rows, "participant_id"),
        "viewpoint": viewpoint_metrics(rows),
        "reliability": reliability_metrics(rows),
    }


def error_rows(rows: list[dict]) -> list[dict]:
    output = []
    for row in rows:
        predicted = _optional_int(row.get("predicted_repetition_count"))
        manual = int(row["manual_repetition_count"])
        signed = predicted - manual if predicted is not None else None
        output.append({
            "session_id": row["session_id"],
            "participant_id": row["participant_id"],
            "manual_viewpoint": row["manual_viewpoint"],
            "predicted_viewpoint": row.get("predicted_viewpoint") or "unavailable",
            "manual_repetition_count": manual,
            "predicted_repetition_count": predicted,
            "signed_error": signed,
            "absolute_error": abs(signed) if signed is not None else None,
            "prediction_confidence": _optional_float(row.get("repetition_confidence")),
            "pose_coverage": _optional_float(row.get("pose_detection_coverage")),
            "phase_signal": row.get("selected_phase_signal") or "unavailable",
            "warnings": row.get("quality_warnings") or "",
            "status": row.get("processing_status"),
        })
    return sorted(output, key=lambda row: (row["absolute_error"] is None, -(row["absolute_error"] or 0), row["session_id"]))


def select_demo_candidates(rows: list[dict], minimum_pose_coverage: float, minimum_count_confidence: float) -> list[dict]:
    eligible = []
    for row in rows:
        predicted = _optional_int(row.get("predicted_repetition_count"))
        pose = _optional_float(row.get("pose_detection_coverage"))
        confidence = _optional_float(row.get("repetition_confidence"))
        if (
            row.get("processing_status") == "success"
            and predicted is not None
            and pose is not None
            and pose >= minimum_pose_coverage
            and confidence is not None
            and confidence >= minimum_count_confidence
            and row.get("selected_phase_signal")
            and row.get("preview_path")
        ):
            candidate = dict(row)
            candidate["absolute_error"] = abs(predicted - int(row["manual_repetition_count"]))
            eligible.append(candidate)
    ordered = sorted(
        eligible,
        key=lambda row: (
            row["absolute_error"],
            -float(row["pose_detection_coverage"]),
            -float(row["repetition_confidence"]),
            row["session_id"],
        ),
    )
    chosen: list[dict] = []
    side = next((row for row in ordered if row["manual_viewpoint"] == "side"), None)
    non_side = next((row for row in ordered if row["manual_viewpoint"] in {"front", "oblique"}), None)
    for candidate in (side, non_side):
        if candidate and candidate not in chosen:
            chosen.append(candidate)
    for candidate in ordered:
        if candidate not in chosen:
            chosen.append(candidate)
        if len(chosen) == 3:
            break
    return chosen


def json_cell(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)
