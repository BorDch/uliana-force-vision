from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from uliana.contracts.models import PressureObservation
from .ingestion import PressureIssue


@dataclass(frozen=True)
class PressureDiagnostics:
    channels_found: list[str]
    duration_ms: int | None
    sampling_rate_hz: dict[str, float | None]
    issues: list[PressureIssue]

    def to_dict(self) -> dict:
        return {"channels_found": self.channels_found, "duration_ms": self.duration_ms,
                "sampling_rate_hz": self.sampling_rate_hz,
                "issues": [issue.__dict__ for issue in self.issues]}


def analyze_pressure_quality(observations: list[PressureObservation], config: dict,
                             ingestion_issues: list[PressureIssue] | None = None) -> PressureDiagnostics:
    issues = list(ingestion_issues or [])
    grouped: dict[tuple[str, str], list[PressureObservation]] = defaultdict(list)
    for item in observations: grouped[(item.sensor_id, item.channel_id)].append(item)
    channels = sorted({item.channel_id for item in observations})
    expected = set(config.get("expected_channels") or [])
    for channel in sorted(expected - set(channels)):
        issues.append(PressureIssue("warning", "missing_channel", "expected channel is absent", channel_id=channel))
    for channel in sorted(set(channels) - expected) if expected else []:
        issues.append(PressureIssue("warning", "unexpected_channel", "channel was not configured", channel_id=channel))
    sensor_ids = {item.sensor_id for item in observations}
    if len(sensor_ids) > 1 and not config.get("allow_multiple_sensor_ids", False):
        issues.append(PressureIssue("warning", "inconsistent_sensor_ids", f"found sensors: {sorted(sensor_ids)}"))
    rates: dict[str, float | None] = {}
    all_times = [item.timestamp_ms for item in observations]
    for (_, channel), items in grouped.items():
        ordered = sorted(items, key=lambda item: item.timestamp_ms)
        times = [item.timestamp_ms for item in ordered]
        positive_gaps = [b - a for a, b in zip(times, times[1:]) if b > a]
        # Effective rate includes dropped intervals; median cadence alone can conceal missing samples.
        rates[channel] = ((len(times) - 1) * 1000 / (times[-1] - times[0])) if len(times) > 1 and times[-1] > times[0] else None
        nominal = config.get("nominal_sampling_rate_hz")
        if nominal and rates[channel] is not None and rates[channel] < nominal * config.get("minimum_sampling_rate_fraction", .8):
            issues.append(PressureIssue("warning", "low_sampling_rate", f"actual rate {rates[channel]:.3f} Hz", channel_id=channel))
        for gap in positive_gaps:
            if gap > config.get("long_gap_ms", 100):
                issues.append(PressureIssue("warning", "long_sampling_gap", f"gap of {gap} ms", channel_id=channel)); break
        lower, upper = config.get("saturation_raw_min"), config.get("saturation_raw_max")
        if any((lower is not None and item.raw_value <= lower) or (upper is not None and item.raw_value >= upper) for item in ordered):
            issues.append(PressureIssue("warning", "saturated_raw_value", "raw value reached configured limit", channel_id=channel))
        tolerance, duration = config.get("stuck_tolerance_raw", 0), config.get("stuck_duration_ms", 500)
        start = 0
        for index in range(1, len(ordered)):
            if abs(ordered[index].raw_value - ordered[index - 1].raw_value) > tolerance: start = index
            elif ordered[index].timestamp_ms - ordered[start].timestamp_ms >= duration:
                issues.append(PressureIssue("warning", "stuck_signal", f"constant for at least {duration} ms", channel_id=channel)); break
        if any(item.grid_position is None for item in ordered):
            issues.append(PressureIssue("warning", "missing_grid_coordinates", "one or more samples lack grid coordinates", channel_id=channel))
        statuses = Counter(item.calibration.status for item in ordered)
        for status, code in (("uncalibrated", "uncalibrated_channel"), ("invalid", "invalid_calibration"), ("expired", "expired_calibration")):
            if statuses[status]: issues.append(PressureIssue("warning", code, f"{statuses[status]} sample(s)", channel_id=channel))
    by_time: dict[int, list[PressureObservation]] = defaultdict(list)
    for item in observations: by_time[item.timestamp_ms].append(item)
    near_zero = False
    for items in by_time.values():
        calibrated = [item.calibrated_force_n for item in items if item.calibrated_force_n is not None]
        if len(calibrated) == len(items) and sum(calibrated) < config.get("near_zero_total_force_n", 20): near_zero = True
        elif not calibrated and sum(abs(item.raw_value) for item in items) < config.get("near_zero_total_raw", 1): near_zero = True
    if near_zero: issues.append(PressureIssue("warning", "near_zero_total_signal", "one or more timestamps have near-zero total signal"))
    return PressureDiagnostics(channels, max(all_times) - min(all_times) if all_times else None, rates, issues)
