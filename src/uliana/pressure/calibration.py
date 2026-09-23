from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from uliana.contracts.models import CalibrationState, PressureObservation
from uliana.contracts.validation import SCHEMA_DIRECTORY
from .ingestion import PressureIssue


@dataclass(frozen=True)
class ChannelCalibration:
    calibration_id: str
    sensor_id: str
    channel_id: str
    tare_raw: float
    newtons_per_raw_unit: float
    valid_raw_min: float
    valid_raw_max: float
    created_at: datetime
    expires_at: datetime | None
    reference_notes: str
    valid: bool = True


@dataclass(frozen=True)
class CalibrationResult:
    observations: list[PressureObservation]
    issues: list[PressureIssue]


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def load_calibrations(path: str | Path) -> tuple[dict[tuple[str, str], ChannelCalibration], list[PressureIssue]]:
    issues: list[PressureIssue] = []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        schema = json.loads((SCHEMA_DIRECTORY / "calibration.schema.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [PressureIssue("error", "calibration_file_invalid", str(exc))]
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0" or not isinstance(payload.get("calibrations"), list):
        return {}, [PressureIssue("error", "calibration_config_invalid", "schema_version 1.0 and calibrations array are required")]
    output = {}
    for item in payload["calibrations"]:
        entry_errors = list(Draft202012Validator(schema["$defs"]["channelCalibration"],
                            format_checker=Draft202012Validator.FORMAT_CHECKER).iter_errors(item))
        if entry_errors:
            sensor, channel = item.get("sensor_id"), item.get("channel_id")
            issues.extend(PressureIssue("error", "calibration_config_invalid", error.message,
                                       channel_id=channel) for error in entry_errors)
            if isinstance(sensor, str) and sensor and isinstance(channel, str) and channel:
                output[(sensor, channel)] = ChannelCalibration(item.get("calibration_id") or "invalid", sensor, channel,
                    0, 1, 0, 1, datetime.min.replace(tzinfo=timezone.utc), None, "malformed calibration", False)
            continue
        try:
            if item["valid_raw_max"] <= item["valid_raw_min"]:
                raise ValueError("valid_raw_max must exceed valid_raw_min")
            value = ChannelCalibration(item["calibration_id"], item["sensor_id"], item["channel_id"],
                item["tare_raw"], item["newtons_per_raw_unit"], item["valid_raw_min"], item["valid_raw_max"],
                _datetime(item["created_at"]), _datetime(item["expires_at"]) if item.get("expires_at") else None,
                item["reference_notes"])
            key = (value.sensor_id, value.channel_id)
            if key in output: raise ValueError(f"duplicate calibration for {key}")
            output[key] = value
        except (TypeError, ValueError) as exc:
            issues.append(PressureIssue("error", "calibration_config_invalid", str(exc), channel_id=item.get("channel_id")))
    return output, issues


def apply_calibration(observations: list[PressureObservation], calibrations: dict[tuple[str, str], ChannelCalibration],
                      at: datetime | None = None, overwrite: bool = False) -> CalibrationResult:
    at = at or datetime.now(timezone.utc)
    if at.tzinfo is None: at = at.replace(tzinfo=timezone.utc)
    output, issues = [], []
    for observation in observations:
        if observation.calibrated_force_n is not None and not overwrite:
            output.append(observation); continue
        calibration = calibrations.get((observation.sensor_id, observation.channel_id))
        if calibration is None:
            output.append(replace(observation, calibrated_force_n=None, calibration=CalibrationState("uncalibrated")))
            issues.append(PressureIssue("warning", "calibration_missing", "no calibration configured", channel_id=observation.channel_id))
            continue
        if not calibration.valid:
            output.append(replace(observation, calibrated_force_n=None,
                                  calibration=CalibrationState("invalid", calibration.calibration_id)))
            issues.append(PressureIssue("warning", "calibration_invalid", "configured calibration is malformed",
                                        channel_id=observation.channel_id))
            continue
        if calibration.expires_at is not None and at > calibration.expires_at:
            output.append(replace(observation, calibrated_force_n=None,
                                  calibration=CalibrationState("expired", calibration.calibration_id)))
            issues.append(PressureIssue("warning", "calibration_expired", "calibration has expired", channel_id=observation.channel_id))
            continue
        outside = not calibration.valid_raw_min <= observation.raw_value <= calibration.valid_raw_max
        force = max(0.0, (observation.raw_value - calibration.tare_raw) * calibration.newtons_per_raw_unit)
        flags = list(observation.quality_flags)
        if outside:
            flags.append("raw_outside_calibration_range")
            issues.append(PressureIssue("warning", "raw_outside_calibration_range",
                                        "calibrated without extrapolation guarantee", channel_id=observation.channel_id))
        output.append(replace(observation, calibrated_force_n=force,
                              calibration=CalibrationState("calibrated", calibration.calibration_id), quality_flags=flags))
    return CalibrationResult(output, issues)
