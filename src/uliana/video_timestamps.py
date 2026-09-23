from __future__ import annotations


def increasing_timestamp_ms(capture_timestamp_ms: float | None, frame_index: int, fps: float, previous_ms: int | None) -> tuple[int, str]:
    """Return source-derived monotonic time and record fallback provenance."""
    if capture_timestamp_ms is not None and capture_timestamp_ms >= 0:
        candidate, source = round(capture_timestamp_ms), "container_timestamp"
    elif fps > 0:
        candidate, source = round(frame_index * 1000 / fps), "frame_index_fps_fallback"
    else:
        raise ValueError("frame has no usable capture timestamp or frame-rate fallback")
    if previous_ms is not None and candidate <= previous_ms:
        candidate, source = previous_ms + 1, f"{source}_monotonic_adjustment"
    return candidate, source

