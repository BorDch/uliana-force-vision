#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uliana.contracts.validation import ContractValidationError, validate_contract

PRESSURE_COLUMNS = ["timestamp_ms", "timestamp_source", "sensor_id", "channel_id", "row", "column",
                    "raw_value", "calibrated_force_n", "calibration_status", "quality_flags"]
REPETITION_COLUMNS = ["rep_id", "start_ms", "bottom_ms", "end_ms", "quality_notes"]
CONDITION_COLUMNS = ["rep_id", "condition", "label", "annotator_id", "confidence", "notes"]
CONDITION_LABELS = {"adequate", "condition_detected", "unavailable", "uncertain", "not_visible"}
CALIBRATION_STATUSES = {"calibrated", "uncalibrated", "expired", "invalid", "unknown"}


@dataclass(frozen=True)
class Finding:
    level: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.path}: {self.message}"


def _finding(findings: list[Finding], level: str, path: Path, message: str) -> None:
    findings.append(Finding(level, str(path), message))


def _session_directories(target: Path) -> tuple[list[Path], Path]:
    target = target.resolve()
    if (target / "metadata.json").exists():
        raw_root = target.parent.parent
        return [target], raw_root
    candidates = sorted(path.parent for path in target.rglob("metadata.json"))
    return candidates, target


def _check_columns(path: Path, required: list[str], findings: list[Finding]) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            missing = [name for name in required if name not in (reader.fieldnames or [])]
            if missing:
                _finding(findings, "ERROR", path, f"missing columns: {', '.join(missing)}")
                return []
            return list(reader)
    except (OSError, csv.Error) as exc:
        _finding(findings, "ERROR", path, f"cannot read CSV: {exc}")
        return []


def _integer(value: str, path: Path, row_number: int, field: str, findings: list[Finding], nullable: bool = False) -> int | None:
    if nullable and not value.strip():
        return None
    try:
        result = int(value)
        if result < 0:
            raise ValueError
        return result
    except ValueError:
        _finding(findings, "ERROR", path, f"row {row_number}: {field} must be a non-negative integer")
        return None


def _number(value: str, path: Path, row_number: int, field: str, findings: list[Finding], nullable: bool = False) -> float | None:
    if nullable and not value.strip():
        return None
    try:
        result = float(value)
        if result != result or result in (float("inf"), float("-inf")):
            raise ValueError
        return result
    except ValueError:
        _finding(findings, "ERROR", path, f"row {row_number}: {field} must be a finite number")
        return None


def validate_pressure(path: Path, session_id: str, findings: list[Finding]) -> None:
    rows = _check_columns(path, PRESSURE_COLUMNS, findings)
    previous: dict[tuple[str, str], int] = {}
    coordinates: dict[tuple[str, str], tuple[int | None, int | None]] = {}
    occupied: dict[tuple[str, int, int], str] = {}
    for number, row in enumerate(rows, 2):
        timestamp = _integer(row["timestamp_ms"], path, number, "timestamp_ms", findings)
        sensor, channel = row["sensor_id"].strip(), row["channel_id"].strip()
        if not row["timestamp_source"].strip() or not sensor or not channel:
            _finding(findings, "ERROR", path, f"row {number}: timestamp_source, sensor_id and channel_id are required")
        key = (sensor, channel)
        if timestamp is not None and key in previous:
            if timestamp == previous[key]:
                _finding(findings, "ERROR", path, f"row {number}: duplicate timestamp {timestamp} for {sensor}/{channel}")
            elif timestamp < previous[key]:
                _finding(findings, "ERROR", path, f"row {number}: non-monotonic timestamp for {sensor}/{channel}")
        if timestamp is not None:
            previous[key] = timestamp
        _number(row["raw_value"], path, number, "raw_value", findings)
        calibrated = _number(row["calibrated_force_n"], path, number, "calibrated_force_n", findings, True)
        status = row["calibration_status"].strip()
        if status not in CALIBRATION_STATUSES:
            _finding(findings, "ERROR", path, f"row {number}: invalid calibration_status {status!r}")
        elif status == "calibrated" and calibrated is None:
            _finding(findings, "ERROR", path, f"row {number}: calibrated status requires calibrated_force_n")
        elif status != "calibrated" and calibrated is not None:
            _finding(findings, "ERROR", path, f"row {number}: {status} observation must not provide calibrated_force_n")
        row_value = _integer(row["row"], path, number, "row", findings, True)
        column_value = _integer(row["column"], path, number, "column", findings, True)
        if (row_value is None) != (column_value is None):
            _finding(findings, "ERROR", path, f"row {number}: row and column must both be present or both be empty")
        position = (row_value, column_value)
        if key in coordinates and coordinates[key] != position:
            _finding(findings, "ERROR", path, f"row {number}: grid position changed for {sensor}/{channel}")
        coordinates[key] = position
        if row_value is not None and column_value is not None:
            cell = (sensor, row_value, column_value)
            if cell in occupied and occupied[cell] != channel:
                _finding(findings, "ERROR", path, f"row {number}: grid cell {row_value},{column_value} maps to multiple channels")
            occupied[cell] = channel
    if not rows:
        _finding(findings, "WARNING", path, "pressure stream has no observations")


def validate_annotations(annotation_dir: Path, expected_repetitions: int | None, findings: list[Finding]) -> None:
    repetitions_path = annotation_dir / "repetitions.csv"
    conditions_path = annotation_dir / "conditions.csv"
    if not annotation_dir.exists():
        _finding(findings, "INFO", annotation_dir, "optional annotations are absent")
        return
    if repetitions_path.exists():
        rows = _check_columns(repetitions_path, REPETITION_COLUMNS, findings)
        seen = set()
        for number, row in enumerate(rows, 2):
            rep_id = _integer(row["rep_id"], repetitions_path, number, "rep_id", findings)
            start = _integer(row["start_ms"], repetitions_path, number, "start_ms", findings)
            bottom = _integer(row["bottom_ms"], repetitions_path, number, "bottom_ms", findings, True)
            end = _integer(row["end_ms"], repetitions_path, number, "end_ms", findings)
            if rep_id in seen:
                _finding(findings, "ERROR", repetitions_path, f"row {number}: duplicate rep_id {rep_id}")
            seen.add(rep_id)
            if start is not None and end is not None and not (start <= (bottom if bottom is not None else end) <= end):
                _finding(findings, "ERROR", repetitions_path, f"row {number}: repetition timestamps are out of order")
        if expected_repetitions is not None and rows and len(rows) != expected_repetitions:
            _finding(findings, "WARNING", repetitions_path, f"annotation count {len(rows)} differs from expected_repetitions {expected_repetitions}")
    else:
        _finding(findings, "INFO", repetitions_path, "optional repetition annotations are absent")
    if conditions_path.exists():
        rows = _check_columns(conditions_path, CONDITION_COLUMNS, findings)
        for number, row in enumerate(rows, 2):
            _integer(row["rep_id"], conditions_path, number, "rep_id", findings)
            if not row["condition"].strip():
                _finding(findings, "ERROR", conditions_path, f"row {number}: condition is required")
            if row["label"].strip() not in CONDITION_LABELS:
                _finding(findings, "ERROR", conditions_path, f"row {number}: invalid condition label {row['label']!r}")
            confidence = _number(row["confidence"], conditions_path, number, "confidence", findings, True)
            if confidence is not None and not 0 <= confidence <= 1:
                _finding(findings, "ERROR", conditions_path, f"row {number}: confidence must be between 0 and 1")
    else:
        _finding(findings, "INFO", conditions_path, "optional condition annotations are absent")


def validate_dataset(target: Path) -> list[Finding]:
    findings: list[Finding] = []
    sessions, raw_root = _session_directories(target)
    if not sessions:
        _finding(findings, "ERROR", target, "no session directories containing metadata.json found")
        return findings
    identities: set[tuple[str, str]] = set()
    session_ids: set[str] = set()
    for session_dir in sessions:
        metadata_path = session_dir / "metadata.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            validate_contract("metadata", metadata)
        except (OSError, json.JSONDecodeError, ContractValidationError) as exc:
            _finding(findings, "ERROR", metadata_path, f"invalid metadata: {exc}")
            continue
        participant_id, session_id = metadata["participant_id"], metadata["session_id"]
        if session_dir.name != session_id or session_dir.parent.name != participant_id:
            _finding(findings, "ERROR", session_dir, "participant/session directory names do not match metadata IDs")
        identity = (participant_id, session_id)
        if identity in identities or session_id in session_ids:
            _finding(findings, "ERROR", session_dir, "participant/session IDs are not unique in this dataset")
        identities.add(identity); session_ids.add(session_id)
        if metadata["consent_status"] != "granted":
            _finding(findings, "ERROR", metadata_path, f"consent_status is {metadata['consent_status']!r}; processing is not permitted")
        video = session_dir / "video.mp4"
        if not video.exists():
            _finding(findings, "ERROR", video, "required video file is missing")
        elif video.stat().st_size == 0:
            _finding(findings, "WARNING" if metadata.get("test_fixture") else "ERROR", video,
                     "empty video is a declared test fixture, not a valid real video" if metadata.get("test_fixture") else "video file is empty")
        elif metadata.get("test_fixture"):
            _finding(findings, "INFO", video, "declared placeholder; video decoding is intentionally not validated as real media")
        pressure = session_dir / "pressure.csv"
        if pressure.exists():
            validate_pressure(pressure, session_id, findings)
        else:
            _finding(findings, "INFO", pressure, "optional pressure stream is absent; pressure assessments will be unavailable")
        annotations_root = raw_root.parent / "annotations"
        validate_annotations(annotations_root / participant_id / session_id, metadata["expected_repetitions"], findings)
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ULIANA raw dataset sessions and optional annotations.")
    parser.add_argument("path", type=Path, help="data/raw or one data/raw/<participant>/<session> directory")
    args = parser.parse_args()
    findings = validate_dataset(args.path)
    for finding in findings:
        print(finding)
    counts = {level: sum(f.level == level for f in findings) for level in ("ERROR", "WARNING", "INFO")}
    print(f"SUMMARY: {counts['ERROR']} error(s), {counts['WARNING']} warning(s), {counts['INFO']} info message(s)")
    return 1 if counts["ERROR"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
