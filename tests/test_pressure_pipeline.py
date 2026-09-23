import json
from datetime import datetime, timezone

import pytest

from uliana.contracts.models import CalibrationState, GridPosition, PressureObservation
from uliana.pressure import (ChannelCalibration, analyze_pressure_quality, apply_calibration,
                             compute_pressure_features, load_calibrations, read_pressure_csv)


def observation(channel, timestamp, raw, force=None, row=0, column=0, status=None, flags=None, sensor="mat"):
    status = status or ("calibrated" if force is not None else "uncalibrated")
    return PressureObservation("1.0", "s", timestamp, "device_clock", sensor, channel, raw, force,
                               CalibrationState(status), GridPosition(row, column), flags or [])


def quality_config(**changes):
    value = {"expected_channels": [], "nominal_sampling_rate_hz": 10, "minimum_sampling_rate_fraction": .8,
             "long_gap_ms": 150, "saturation_raw_min": 0, "saturation_raw_max": 1000,
             "stuck_tolerance_raw": 0, "stuck_duration_ms": 200, "near_zero_total_force_n": 1,
             "near_zero_total_raw": 1, "minimum_region_coverage": .7, "imbalance_alert_percent": 10}
    value.update(changes); return value


def test_four_cells_and_two_sensors_may_share_timestamps(tmp_path):
    path = tmp_path / "pressure.csv"
    path.write_text("timestamp_ms,timestamp_source,sensor_id,channel_id,row,column,raw_value,calibrated_force_n,calibration_status,quality_flags\n" +
        "\n".join(f"0,device_clock,{('mat-a' if i < 2 else 'mat-b')},cell_{i},0,{i},10,,uncalibrated," for i in range(4)) + "\n")
    result = read_pressure_csv(path, "s")
    assert not result.errors and len(result.observations) == 4


def test_ingestion_non_monotonic_duplicate_malformed_and_camera_only(tmp_path):
    assert read_pressure_csv(tmp_path / "absent.csv", "s").issues[0].code == "pressure_stream_absent"
    path = tmp_path / "pressure.csv"
    path.write_text("timestamp_ms,timestamp_source,sensor_id,channel_id,row,column,raw_value,calibrated_force_n,calibration_status,quality_flags\n"
                    "20,clock,mat,c,0,0,1,,uncalibrated,\n20,clock,mat,c,0,0,2,,uncalibrated,\n10,clock,mat,c,0,0,3,,uncalibrated,\nbad,clock,mat,c,0,,x,,uncalibrated,\n")
    codes = {issue.code for issue in read_pressure_csv(path, "s").errors}
    assert {"duplicate_channel_timestamp", "non_monotonic_channel_timestamp", "malformed_row"} <= codes


def test_per_channel_calibration_missing_expired_and_raw_range():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    valid = ChannelCalibration("c1", "mat", "a", 10, .5, 0, 100, now, None, "reference")
    expired = ChannelCalibration("c2", "mat", "b", 0, 1, 0, 100, now, datetime(2026, 1, 2, tzinfo=timezone.utc), "reference")
    items = [observation("a", 0, 20), observation("a", 10, 110), observation("b", 0, 20), observation("missing", 0, 20)]
    result = apply_calibration(items, {("mat", "a"): valid, ("mat", "b"): expired},
                               at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert result.observations[0].calibrated_force_n == 5
    assert result.observations[1].calibrated_force_n == 50
    assert "raw_outside_calibration_range" in result.observations[1].quality_flags
    assert result.observations[2].calibration.status == "expired" and result.observations[2].calibrated_force_n is None
    assert result.observations[3].calibration.status == "uncalibrated"


def test_existing_calibration_is_not_overwritten():
    calibration = ChannelCalibration("c", "mat", "a", 0, 2, 0, 100, datetime.now(timezone.utc), None, "")
    result = apply_calibration([observation("a", 0, 10, 123)], {("mat", "a"): calibration})
    assert result.observations[0].calibrated_force_n == 123


def test_malformed_calibration_marks_matching_observation_invalid(tmp_path):
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps({"schema_version": "1.0", "calibrations": [{"calibration_id": "bad",
        "sensor_id": "mat", "channel_id": "a", "tare_raw": 0, "newtons_per_raw_unit": 0,
        "valid_raw_min": 0, "valid_raw_max": 100, "created_at": "2026-01-01T00:00:00Z", "reference_notes": "bad"}]}))
    calibrations, issues = load_calibrations(path)
    result = apply_calibration([observation("a", 0, 10)], calibrations)
    assert issues and result.observations[0].calibration.status == "invalid"


def test_quality_detects_saturation_stuck_and_dropped_samples():
    items = [observation("a", t, raw, raw) for t, raw in ((0, 1000), (100, 5), (200, 5), (500, 5))]
    diagnostics = analyze_pressure_quality(items, quality_config())
    codes = {issue.code for issue in diagnostics.issues}
    assert {"saturated_raw_value", "stuck_signal", "long_sampling_gap", "low_sampling_rate"} <= codes


def test_centre_of_pressure_channel_features_and_region_balance():
    items = []
    for timestamp in (0, 100):
        items += [observation("cell_00", timestamp, 10, 10, 0, 0), observation("cell_01", timestamp, 30, 30, 0, 1),
                  observation("cell_02", timestamp, 20, 20, 1, 0), observation("cell_03", timestamp, 20, 20, 1, 1)]
    config = quality_config(regions={"left_palm": ["cell_00", "cell_01"], "right_palm": ["cell_02", "cell_03"]})
    features = compute_pressure_features(items, config)
    first = features["time_series"][0]
    assert first["total_calibrated_force_n"] == 80
    assert first["centre_of_pressure"] == {"row": .5, "column": .625}
    assert features["region_balance"]["imbalance_percent"] == 0
    assert features["per_channel"]["cell_00"]["impulse_ns"] == pytest.approx(1)


def test_raw_centre_is_explicitly_non_physical_and_balance_can_be_unavailable():
    items = [observation("a", 0, 1, row=0, column=0), observation("b", 0, 3, row=0, column=1)]
    features = compute_pressure_features(items, quality_config(regions={"left_palm": ["a"], "right_palm": ["b"]}), True)
    assert features["time_series"][0]["centre_kind"] == "raw_signal_weighted_non_physical"
    assert features["region_balance"]["reason"] == "required_region_channels_uncalibrated"


def test_balance_unavailable_for_missing_region_channel():
    features = compute_pressure_features([observation("a", 0, 1, 1)],
        quality_config(regions={"left_palm": ["a"], "right_palm": ["b"]}))
    assert features["region_balance"]["reason"] == "required_region_channels_missing"
