from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass

from uliana.contracts.models import PressureObservation
from uliana.metrics import moving_average
from uliana.types import ForceSample, PoseSample, SynchronizedSample
from .alignment import Alignment


@dataclass(frozen=True)
class AlignedPressureFrame:
    video_timestamp_ms: int
    channels: dict[str, dict]


def _usable(item: PressureObservation) -> bool:
    bad = {"saturated_raw_value", "invalid_sample", "sensor_error"}
    return item.calibration.status != "invalid" and not bad.intersection(item.quality_flags)


def interpolate_pressure(video_timestamps_ms: list[int], observations: list[PressureObservation],
                         alignment: Alignment, maximum_gap_ms: int) -> tuple[list[AlignedPressureFrame], dict]:
    if not alignment.available:
        return [AlignedPressureFrame(t, {}) for t in video_timestamps_ms], {"matched_fraction": 0.0, "errors_ms": [], "maximum_gap_ms": None}
    grouped = defaultdict(list)
    for item in observations:
        aligned = alignment.pressure_to_video_ms(item.timestamp_ms)
        grouped[item.channel_id].append((aligned, item))
    for items in grouped.values(): items.sort(key=lambda pair: pair[0])
    frames, errors, used_gaps = [], [], []
    for target in video_timestamps_ms:
        channels = {}
        for channel, items in grouped.items():
            before = next(((t, item) for t, item in reversed(items) if t <= target), None)
            after = next(((t, item) for t, item in items if t >= target), None)
            selected = None
            if before and after and before[0] != after[0]:
                gap = after[0] - before[0]
                if gap <= maximum_gap_ms and _usable(before[1]) and _usable(after[1]):
                    ratio = (target - before[0]) / gap
                    calibrated = None
                    if before[1].calibrated_force_n is not None and after[1].calibrated_force_n is not None:
                        calibrated = before[1].calibrated_force_n + ratio * (after[1].calibrated_force_n - before[1].calibrated_force_n)
                    selected = {"raw_value": before[1].raw_value + ratio * (after[1].raw_value - before[1].raw_value),
                                "calibrated_force_n": calibrated, "method": "interpolated", "distance_ms": 0.0}
                    used_gaps.append(gap)
            else:
                boundary = before or after
                if boundary and abs(boundary[0] - target) <= maximum_gap_ms and _usable(boundary[1]):
                    selected = {"raw_value": boundary[1].raw_value, "calibrated_force_n": boundary[1].calibrated_force_n,
                                "method": "bounded_nearest_boundary", "distance_ms": abs(boundary[0] - target)}
                    errors.append(abs(boundary[0] - target)); used_gaps.append(abs(boundary[0] - target))
            if before and after and before[0] == after[0] and abs(before[0] - target) <= maximum_gap_ms and _usable(before[1]):
                selected = {"raw_value": before[1].raw_value, "calibrated_force_n": before[1].calibrated_force_n,
                            "method": "exact", "distance_ms": abs(before[0] - target)}
                errors.append(abs(before[0] - target)); used_gaps.append(abs(before[0] - target))
            if selected is not None: channels[channel] = selected
        frames.append(AlignedPressureFrame(target, channels))
    total = len(video_timestamps_ms) * len(grouped)
    matched = sum(len(frame.channels) for frame in frames)
    return frames, {"matched_fraction": matched / total if total else 0.0, "errors_ms": errors,
                    "maximum_gap_ms": max(used_gaps) if used_gaps else None}


def legacy_nearest_synchronize(pose_samples: list[PoseSample], force_samples: list[ForceSample],
                               max_difference_ms: int = 50, smoothing_window: int = 5) -> tuple[list[SynchronizedSample], dict]:
    """Original unrestricted nearest-neighbour matcher retained only for compatibility."""
    forces = sorted(force_samples, key=lambda x: x.timestamp_ms)
    output, errors, left_history, right_history = [], [], [], []
    cursor = 0
    for pose in sorted(pose_samples, key=lambda x: x.timestamp_ms):
        while cursor + 1 < len(forces) and abs(forces[cursor + 1].timestamp_ms - pose.timestamp_ms) <= abs(forces[cursor].timestamp_ms - pose.timestamp_ms): cursor += 1
        force = forces[cursor] if forces else None
        difference = abs(force.timestamp_ms - pose.timestamp_ms) if force else None
        if difference is None or difference > max_difference_ms: output.append(SynchronizedSample(pose, None, None))
        else:
            errors.append(difference); left_history.append(force.left_force_n); right_history.append(force.right_force_n)
            left_history = left_history[-smoothing_window:]; right_history = right_history[-smoothing_window:]
            output.append(SynchronizedSample(pose, force, difference, force.left_force_n, force.right_force_n,
                moving_average(left_history, len(left_history))[-1], moving_average(right_history, len(right_history))[-1]))
    ordered = sorted(errors); p95 = ordered[min(len(ordered) - 1, int(.95 * len(ordered)))] if ordered else None
    return output, {"pose_observations": len(pose_samples), "matched": len(errors), "missing_matches": len(pose_samples)-len(errors),
        "synchronized_percent": 100*len(errors)/len(pose_samples) if pose_samples else 0,
        "mean_error_ms": statistics.fmean(errors) if errors else None, "median_error_ms": statistics.median(errors) if errors else None,
        "p95_error_ms": p95}
