from __future__ import annotations

import statistics

from .types import ForceSample, PoseSample, SynchronizedSample


def synchronize(pose_samples: list[PoseSample], force_samples: list[ForceSample], max_difference_ms: int = 50, smoothing_window: int = 5) -> tuple[list[SynchronizedSample], dict]:
    forces = sorted(force_samples, key=lambda x: x.timestamp_ms)
    output, errors, left_history, right_history = [], [], [], []
    cursor = 0
    for pose in sorted(pose_samples, key=lambda x: x.timestamp_ms):
        while cursor + 1 < len(forces) and abs(forces[cursor + 1].timestamp_ms - pose.timestamp_ms) <= abs(forces[cursor].timestamp_ms - pose.timestamp_ms):
            cursor += 1
        force = forces[cursor] if forces else None
        difference = abs(force.timestamp_ms - pose.timestamp_ms) if force else None
        if difference is None or difference > max_difference_ms:
            output.append(SynchronizedSample(pose, None, None))
        else:
            errors.append(difference)
            left_history.append(force.left_force_n); right_history.append(force.right_force_n)
            left_history = left_history[-smoothing_window:]; right_history = right_history[-smoothing_window:]
            output.append(SynchronizedSample(pose, force, difference, force.left_force_n, force.right_force_n,
                                             sum(left_history) / len(left_history), sum(right_history) / len(right_history)))
    ordered = sorted(errors)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))] if ordered else None
    stats = {
        "pose_observations": len(pose_samples), "matched": len(errors), "missing_matches": len(pose_samples) - len(errors),
        "synchronized_percent": 100 * len(errors) / len(pose_samples) if pose_samples else 0,
        "mean_error_ms": statistics.fmean(errors) if errors else None,
        "median_error_ms": statistics.median(errors) if errors else None, "p95_error_ms": p95,
    }
    return output, stats
