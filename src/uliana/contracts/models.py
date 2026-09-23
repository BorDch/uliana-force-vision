from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Viewpoint = Literal["side", "front", "oblique", "unknown"]
AssessmentValue = Literal["adequate", "condition_detected", "unavailable"]
CalibrationStatus = Literal["calibrated", "uncalibrated", "expired", "invalid", "unknown"]
ConsentStatus = Literal["granted", "denied", "withdrawn", "unknown"]


class ContractModel:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LandmarkObservation(ContractModel):
    x: float
    y: float
    z: float | None = None
    visibility: float | None = None
    presence: float | None = None


@dataclass(frozen=True)
class PoseObservation(ContractModel):
    detected: bool
    landmarks: dict[str, LandmarkObservation] = field(default_factory=dict)
    model_confidence: float | None = None
    raw_landmarks: dict[str, LandmarkObservation] | None = None
    world_landmarks: dict[str, LandmarkObservation] | None = None
    world_landmarks_caveat: str | None = None


@dataclass(frozen=True)
class ViewpointEstimate(ContractModel):
    value: Viewpoint
    confidence: float | None = None
    reason: str | None = None


@dataclass(frozen=True)
class VideoObservation(ContractModel):
    schema_version: str
    session_id: str
    frame_index: int
    timestamp_ms: int
    timestamp_source: str
    fps: float
    image_width_px: int
    image_height_px: int
    pose: PoseObservation
    viewpoint: ViewpointEstimate
    quality_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CalibrationState(ContractModel):
    status: CalibrationStatus
    calibration_id: str | None = None


@dataclass(frozen=True)
class GridPosition(ContractModel):
    row: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class PressureObservation(ContractModel):
    schema_version: str
    session_id: str
    timestamp_ms: int
    timestamp_source: str
    sensor_id: str
    channel_id: str
    raw_value: float
    calibrated_force_n: float | None
    calibration: CalibrationState
    grid_position: GridPosition | None = None
    quality_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RepetitionInterval(ContractModel):
    rep_id: int
    start_ms: int
    bottom_ms: int | None
    end_ms: int
    confidence: float | None = None
    selected_phase_signal: str | None = None
    quality_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssessmentResult(ContractModel):
    condition: str
    result: AssessmentValue
    confidence: float | None
    reason: str | None = None
    rep_id: int | None = None
    modality: Literal["camera", "pressure", "multimodal"] | None = None
    evidence: dict[str, Any] | None = None


@dataclass(frozen=True)
class SynchronizationReport(ContractModel):
    status: Literal["not_applicable", "acceptable", "poor", "unavailable"]
    method: str | None = None
    estimated_offset_ms: float | None = None
    estimated_drift_ppm: float | None = None
    matched_fraction: float | None = None
    median_error_ms: float | None = None
    p95_error_ms: float | None = None
    reason: str | None = None
    maximum_gap_ms: float | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SessionResult(ContractModel):
    schema_version: str
    session_id: str
    mode: Literal["camera_only", "pressure_only", "multimodal"]
    repetition_count: int | None
    repetition_intervals: list[RepetitionInterval]
    detected_viewpoint: ViewpointEstimate
    assessments: list[AssessmentResult]
    pressure_features: dict[str, float | int | str | None] | None
    synchronization: SynchronizationReport
    overall_assessment_coverage: float
    warnings: list[str] = field(default_factory=list)
    unavailable_assessments: list[AssessmentResult] = field(default_factory=list)
    viewpoint_changes: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    repetition_results: list[dict[str, Any]] = field(default_factory=list)
    primary_cue: dict[str, Any] | None = None
    repeated_conditions: list[str] = field(default_factory=list)
    modality_availability: dict[str, bool] = field(default_factory=dict)
    coverage: dict[str, float] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SessionMetadata(ContractModel):
    schema_version: str
    participant_id: str
    session_id: str
    experience_level: Literal["beginner", "intermediate", "advanced", "unknown"]
    camera_viewpoint: Viewpoint
    exercise_variation: str
    expected_repetitions: int | None
    intentionally_performed_condition: str | None
    consent_status: ConsentStatus
    hardware_configuration: dict[str, Any]
    notes: str
    split: Literal["development", "test", "unassigned"] = "unassigned"
    test_fixture: bool = False
    synchronization: dict[str, Any] | None = None
