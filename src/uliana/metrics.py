from __future__ import annotations

import math
from collections.abc import Iterable


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def asymmetry_percent(left_force: float, right_force: float, near_zero_n: float = 20.0) -> float | None:
    if not all(math.isfinite(v) and v >= 0 for v in (left_force, right_force)):
        raise ValueError("force values must be finite and non-negative")
    total = left_force + right_force
    if total < near_zero_n:
        return None
    return abs(left_force - right_force) / total * 100.0


def moving_average(values: Iterable[float], window: int) -> list[float]:
    if window < 1:
        raise ValueError("window must be positive")
    result, active = [], []
    for value in values:
        active.append(value)
        if len(active) > window:
            active.pop(0)
        result.append(sum(active) / len(active))
    return result


def impulse(samples: list[tuple[int, float]]) -> float:
    return sum((b_t - a_t) / 1000 * (a_v + b_v) / 2 for (a_t, a_v), (b_t, b_v) in zip(samples, samples[1:]))


def persistent(values: list[tuple[int, bool]], duration_ms: int) -> bool:
    start = None
    for timestamp, active in values:
        start = timestamp if active and start is None else start
        if not active:
            start = None
        elif timestamp - start >= duration_ms:
            return True
    return False

