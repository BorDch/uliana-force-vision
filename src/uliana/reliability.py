from __future__ import annotations

import math

from .types import ReliabilityState, SynchronizedSample


def assess(samples: list[SynchronizedSample], config: dict) -> ReliabilityState:
    limits = config["reliability"]
    if not samples:
        return ReliabilityState(False, "missing_measurements", False, False)
    pose_ok = sum(s.pose.confidence >= limits["min_pose_confidence"] for s in samples) / len(samples) >= 0.7
    matched = [s.force for s in samples if s.force is not None]
    coverage = len(matched) / len(samples)
    force_ok = coverage >= limits["min_synchronized_fraction"]
    reason = None
    if force_ok:
        for force in matched:
            values = (force.left_force_n, force.right_force_n)
            if (not force.valid or not all(math.isfinite(x) for x in values)
                    or any(x < 0 or x >= limits["max_force_n"] for x in values)
                    or sum(values) < limits["min_total_force_n"]):
                force_ok, reason = False, force.error or "invalid_or_saturated_force"
                break
    if not force_ok and reason is None:
        reason = "insufficient_force_coverage"
    if force_ok and not pose_ok:
        reason = "pose_confidence_below_limit"
    return ReliabilityState(force_ok and pose_ok, reason, pose_ok, force_ok)

