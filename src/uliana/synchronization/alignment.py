from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Alignment:
    method: str
    available: bool
    offset_ms: float | None
    scale: float | None
    drift_ppm: float | None
    anchor_residuals_ms: list[float]
    warnings: list[str]
    reason: str | None = None

    def pressure_to_video_ms(self, timestamp_ms: int | float) -> float | None:
        return self.scale * timestamp_ms + self.offset_ms if self.available else None


def estimate_alignment(mode: str, configured_offset_ms: float | None = None,
                       anchors: list[dict[str, float]] | None = None) -> Alignment:
    anchors = anchors or []
    if mode == "shared_relative_clock":
        return Alignment(mode, True, 0.0, 1.0, 0.0, [], [])
    if mode == "configured_constant_offset":
        if configured_offset_ms is None:
            return Alignment(mode, False, None, None, None, [], [], "configured_offset_missing")
        return Alignment(mode, True, float(configured_offset_ms), 1.0, 0.0, [], [])
    if mode == "shared_synchronization_event":
        if len(anchors) != 1:
            return Alignment(mode, False, None, None, None, [], [], "exactly_one_anchor_required")
        offset = anchors[0]["video_timestamp_ms"] - anchors[0]["pressure_timestamp_ms"]
        return Alignment(mode, True, offset, 1.0, None, [0.0], [])
    if mode == "linear_anchors":
        if len(anchors) < 2:
            return Alignment(mode, False, None, None, None, [], [], "at_least_two_anchors_required")
        xs = [float(a["pressure_timestamp_ms"]) for a in anchors]
        ys = [float(a["video_timestamp_ms"]) for a in anchors]
        mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
        denominator = sum((x - mean_x) ** 2 for x in xs)
        if denominator == 0:
            return Alignment(mode, False, None, None, None, [], [], "pressure_anchor_times_not_distinct")
        scale = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
        if scale <= 0:
            return Alignment(mode, False, None, None, None, [], [], "invalid_clock_scale")
        offset = mean_y - scale * mean_x
        residuals = [abs((scale * x + offset) - y) for x, y in zip(xs, ys)]
        return Alignment(mode, True, offset, scale, (scale - 1.0) * 1_000_000, residuals, [])
    if mode == "unavailable":
        return Alignment(mode, False, None, None, None, [], [], "clock_relationship_unavailable")
    return Alignment(mode, False, None, None, None, [], [], "unknown_alignment_mode")
