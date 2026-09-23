from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Phase = Literal["up", "down", "transition"]


@dataclass(frozen=True)
class ForceSample:
    timestamp_ms: int
    left_force_n: float
    right_force_n: float
    valid: bool = True
    error: str | None = None


@dataclass(frozen=True)
class PoseSample:
    timestamp_ms: int
    elbow_angle_deg: float
    body_line_error_deg: float
    confidence: float


@dataclass(frozen=True)
class SynchronizedSample:
    pose: PoseSample
    force: ForceSample | None
    timestamp_difference_ms: int | None
    raw_left_force_n: float | None = None
    raw_right_force_n: float | None = None
    filtered_left_force_n: float | None = None
    filtered_right_force_n: float | None = None


@dataclass(frozen=True)
class ReliabilityState:
    reliable: bool
    reason: str | None
    pose_reliable: bool
    force_reliable: bool


@dataclass(frozen=True)
class FeedbackDecision:
    cue: str
    confidence: float
    abstained: bool
    reason: str | None


@dataclass(frozen=True)
class RepetitionSummary:
    rep_id: int
    mean_left_force_n: float | None
    mean_right_force_n: float | None
    mean_asymmetry_percent: float | None
    max_asymmetry_percent: float | None
    left_impulse_ns: float | None
    right_impulse_ns: float | None
    minimum_elbow_angle_deg: float
    maximum_body_line_error_deg: float
    mean_pose_confidence: float
    asymmetry_persistent_ms: int = 1_000_000
    body_line_error_persistent_ms: int = 1_000_000


@dataclass(frozen=True)
class AnalysisResult:
    schema_version: str
    source: str
    session_id: str
    timestamp_ms: int
    rep_id: int
    phase: Phase
    measurements: dict
    quality: dict
    decision: dict

    def to_dict(self) -> dict:
        return asdict(self)
