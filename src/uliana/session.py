from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .metrics import asymmetry_percent, impulse
from .types import AnalysisResult, RepetitionSummary, SynchronizedSample


def _longest_duration(samples: list[tuple[int, bool]]) -> int:
    start = None
    longest = 0
    for timestamp, active in samples:
        if active and start is None: start = timestamp
        if active: longest = max(longest, timestamp - start)
        if not active: start = None
    return longest


def summarize(rep_id: int, samples: list[SynchronizedSample], near_zero_n: float = 20, thresholds: dict | None = None) -> RepetitionSummary:
    thresholds = thresholds or {"asymmetry_percent": 10, "body_line_error_deg": 8}
    matched = [s for s in samples if s.force is not None]
    asymmetries = [a for s in matched if (a := asymmetry_percent(s.filtered_left_force_n, s.filtered_right_force_n, near_zero_n)) is not None]
    left = [(s.pose.timestamp_ms, s.filtered_left_force_n) for s in matched]
    right = [(s.pose.timestamp_ms, s.filtered_right_force_n) for s in matched]
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    return RepetitionSummary(
        rep_id, mean([s.filtered_left_force_n for s in matched]), mean([s.filtered_right_force_n for s in matched]),
        mean(asymmetries), max(asymmetries) if asymmetries else None, impulse(left) if left else None,
        impulse(right) if right else None, min(s.pose.elbow_angle_deg for s in samples),
        max(s.pose.body_line_error_deg for s in samples), mean([s.pose.confidence for s in samples]) or 0,
        _longest_duration([(s.pose.timestamp_ms, (asymmetry_percent(s.filtered_left_force_n, s.filtered_right_force_n, near_zero_n) or 0) > thresholds["asymmetry_percent"]) for s in matched]),
        _longest_duration([(s.pose.timestamp_ms, s.pose.body_line_error_deg > thresholds["body_line_error_deg"]) for s in samples]),
    )


def write_jsonl(path: str | Path, packets: list[AnalysisResult]) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        for packet in packets:
            handle.write(json.dumps(packet.to_dict(), separators=(",", ":"), allow_nan=False) + "\n")
