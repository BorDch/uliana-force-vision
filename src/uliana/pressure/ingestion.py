from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from uliana.contracts.models import CalibrationState, GridPosition, PressureObservation

CANONICAL_COLUMNS = ("timestamp_ms", "timestamp_source", "sensor_id", "channel_id", "row", "column",
                     "raw_value", "calibrated_force_n", "calibration_status", "quality_flags")
CALIBRATION_STATUSES = {"calibrated", "uncalibrated", "expired", "invalid", "unknown"}


@dataclass(frozen=True)
class PressureIssue:
    severity: str
    code: str
    message: str
    row_number: int | None = None
    channel_id: str | None = None


@dataclass
class PressureIngestionResult:
    observations: list[PressureObservation] = field(default_factory=list)
    issues: list[PressureIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[PressureIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[PressureIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]


class PressureAdapter(Protocol):
    """Future device adapters convert their documented native format into this canonical result."""

    def read(self, path: str | Path, session_id: str) -> PressureIngestionResult: ...


def _issue(result: PressureIngestionResult, severity: str, code: str, message: str,
           row: int | None = None, channel: str | None = None) -> None:
    result.issues.append(PressureIssue(severity, code, message, row, channel))


class CanonicalPressureCsvAdapter:
    """Reader for the documented canonical CSV only; it deliberately makes no hardware-format guesses."""

    def read(self, path: str | Path, session_id: str) -> PressureIngestionResult:
        source = Path(path)
        result = PressureIngestionResult()
        if not source.exists():
            _issue(result, "info", "pressure_stream_absent", "optional pressure.csv is absent")
            return result
        try:
            handle = source.open(newline="", encoding="utf-8")
        except OSError as exc:
            _issue(result, "error", "pressure_file_unreadable", str(exc))
            return result
        with handle:
            reader = csv.DictReader(handle)
            missing = [name for name in CANONICAL_COLUMNS if name not in (reader.fieldnames or [])]
            if missing:
                _issue(result, "error", "missing_columns", f"missing columns: {', '.join(missing)}", 1)
                return result
            previous: dict[tuple[str, str], int] = {}
            for row_number, row in enumerate(reader, 2):
                try:
                    timestamp = int(row["timestamp_ms"])
                    if timestamp < 0: raise ValueError("timestamp_ms must be non-negative")
                    raw = float(row["raw_value"])
                    if not (raw == raw and abs(raw) != float("inf")): raise ValueError("raw_value must be finite")
                    calibrated = None if not row["calibrated_force_n"].strip() else float(row["calibrated_force_n"])
                    if calibrated is not None and (calibrated < 0 or calibrated != calibrated or calibrated == float("inf")):
                        raise ValueError("calibrated_force_n must be finite and non-negative")
                    sensor, channel = row["sensor_id"].strip(), row["channel_id"].strip()
                    timestamp_source = row["timestamp_source"].strip()
                    if not sensor or not channel or not timestamp_source:
                        raise ValueError("timestamp_source, sensor_id and channel_id are required")
                    row_text, column_text = row["row"].strip(), row["column"].strip()
                    if bool(row_text) != bool(column_text):
                        raise ValueError("row and column must both be present or both be empty")
                    grid = None
                    if row_text:
                        grid = GridPosition(int(row_text), int(column_text))
                        if grid.row < 0 or grid.column < 0: raise ValueError("grid coordinates must be non-negative")
                    status = row["calibration_status"].strip()
                    if status not in CALIBRATION_STATUSES: raise ValueError(f"invalid calibration_status {status!r}")
                    if status == "calibrated" and calibrated is None:
                        raise ValueError("calibrated status requires calibrated_force_n")
                    if status != "calibrated" and calibrated is not None:
                        raise ValueError(f"{status} status requires empty calibrated_force_n")
                    flags = [flag.strip() for flag in row["quality_flags"].split("|") if flag.strip()]
                except (TypeError, ValueError) as exc:
                    _issue(result, "error", "malformed_row", str(exc), row_number, row.get("channel_id") or None)
                    continue
                key = (sensor, channel)
                if key in previous and timestamp == previous[key]:
                    _issue(result, "error", "duplicate_channel_timestamp", f"duplicate timestamp {timestamp}", row_number, channel)
                elif key in previous and timestamp < previous[key]:
                    _issue(result, "error", "non_monotonic_channel_timestamp", f"timestamp {timestamp} follows {previous[key]}", row_number, channel)
                previous[key] = timestamp
                result.observations.append(PressureObservation("1.0", session_id, timestamp, timestamp_source,
                    sensor, channel, raw, calibrated, CalibrationState(status), grid, flags))
        if not result.observations and not result.errors:
            _issue(result, "warning", "pressure_stream_empty", "pressure.csv contains no observations")
        return result


def read_pressure_csv(path: str | Path, session_id: str) -> PressureIngestionResult:
    return CanonicalPressureCsvAdapter().read(path, session_id)
