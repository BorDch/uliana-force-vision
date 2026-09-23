import pytest

from uliana.contracts.models import CalibrationState, GridPosition, PressureObservation
from uliana.synchronization import estimate_alignment, interpolate_pressure, synchronize, synchronization_report
from uliana.types import ForceSample, PoseSample


def pressure(timestamp, value, flags=None):
    return PressureObservation("1.0", "s", timestamp, "device", "mat", "cell", value, value,
                               CalibrationState("calibrated"), GridPosition(0, 0), flags or [])


def test_shared_clock_and_constant_offset_are_exact():
    shared = estimate_alignment("shared_relative_clock")
    assert shared.pressure_to_video_ms(10) == 10
    offset = estimate_alignment("configured_constant_offset", 100)
    frames, stats = interpolate_pressure([100], [pressure(0, 5)], offset, 10)
    assert frames[0].channels["cell"]["method"] == "exact" and stats["matched_fraction"] == 1


def test_shared_event_and_unavailable_alignment():
    event = estimate_alignment("shared_synchronization_event", anchors=[{"pressure_timestamp_ms": 20, "video_timestamp_ms": 50}])
    assert event.offset_ms == 30
    assert synchronization_report(estimate_alignment("unavailable")).status == "unavailable"


def test_drift_recovery_from_multiple_anchors():
    alignment = estimate_alignment("linear_anchors", anchors=[
        {"pressure_timestamp_ms": 0, "video_timestamp_ms": 10},
        {"pressure_timestamp_ms": 1000, "video_timestamp_ms": 1011},
        {"pressure_timestamp_ms": 2000, "video_timestamp_ms": 2012}])
    assert alignment.offset_ms == pytest.approx(10)
    assert alignment.drift_ppm == pytest.approx(1000)


def test_interpolation_and_large_gap_rejection():
    alignment = estimate_alignment("shared_relative_clock")
    frames, _ = interpolate_pressure([50], [pressure(0, 0), pressure(100, 10)], alignment, 100)
    assert frames[0].channels["cell"]["calibrated_force_n"] == 5
    frames, _ = interpolate_pressure([500], [pressure(0, 0), pressure(1000, 10)], alignment, 100)
    assert frames[0].channels == {}


def test_invalid_sample_prevents_interpolation():
    frames, _ = interpolate_pressure([50], [pressure(0, 0), pressure(100, 10, ["saturated_raw_value"])],
                                     estimate_alignment("shared_relative_clock"), 100)
    assert frames[0].channels == {}


def test_legacy_nearest_compatibility():
    poses = [PoseSample(10, 160, 2, .9)]
    forces = [ForceSample(12, 10, 11)]
    matched, stats = synchronize(poses, forces, 5)
    assert matched[0].force is forces[0] and stats["matched"] == 1
