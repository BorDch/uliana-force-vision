from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventMatch:
    annotation_index: int
    detection_index: int
    timing_error_seconds: float


def match_events(annotated_bottom_seconds: list[float], detected_bottom_seconds: list[float], tolerance_seconds: float) -> list[EventMatch]:
    """Greedy closest one-to-one matching within a documented temporal tolerance."""
    candidates = sorted((abs(a - d), ai, di) for ai, a in enumerate(annotated_bottom_seconds)
                        for di, d in enumerate(detected_bottom_seconds) if abs(a - d) <= tolerance_seconds)
    used_a, used_d, matches = set(), set(), []
    for error, ai, di in candidates:
        if ai not in used_a and di not in used_d:
            used_a.add(ai); used_d.add(di)
            matches.append(EventMatch(ai, di, error))
    return sorted(matches, key=lambda item: item.annotation_index)

