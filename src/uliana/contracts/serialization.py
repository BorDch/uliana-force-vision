from __future__ import annotations

from typing import Any

from .models import (
    AssessmentResult, CalibrationState, GridPosition, LandmarkObservation, PoseObservation,
    PressureObservation, RepetitionInterval, SessionResult, SynchronizationReport,
    VideoObservation, ViewpointEstimate,
)


def from_pose_frame(frame: Any, session_id: str, fps: float, width: int, height: int,
                    viewpoint: str = "unknown") -> VideoObservation:
    """Adapt the legacy PoseFrame; dimensions/FPS/viewpoint were not stored in that type."""
    landmarks = {name: LandmarkObservation(point.x, point.y, point.z, point.visibility, point.presence)
                 for name, point in frame.landmarks.items()}
    world = {name: LandmarkObservation(point.x, point.y, point.z, point.visibility, point.presence)
             for name, point in (frame.world_landmarks or {}).items()} or None
    flags = ([frame.error] if frame.error else []) + ([] if frame.detected else ["pose_not_detected"])
    return VideoObservation("1.0", session_id, frame.frame_index, frame.timestamp_ms, frame.timestamp_source,
                            fps, width, height, PoseObservation(frame.detected, landmarks, None, landmarks.copy(), world,
                            "MediaPipe monocular world coordinates are model estimates, not ground-truth motion capture." if world else None),
                            ViewpointEstimate(viewpoint), flags)


def from_pose_sample(sample: Any, session_id: str, frame_index: int, fps: float,
                     width: int = 1, height: int = 1) -> VideoObservation:
    """Adapt synthetic PoseSample. It has features, not landmarks, so pose quality is retained only as confidence."""
    return VideoObservation("1.0", session_id, frame_index, sample.timestamp_ms, "legacy_sample_timestamp",
                            fps, width, height, PoseObservation(True, {}, sample.confidence),
                            ViewpointEstimate("unknown"), ["legacy_features_only"])


def from_force_sample(sample: Any, session_id: str, sensor_id: str = "legacy_two_channel") -> list[PressureObservation]:
    """Expand the legacy paired force sample into two ordinary channel observations."""
    status = "calibrated" if sample.valid else "invalid"
    flags = [sample.error or "legacy_force_invalid"] if not sample.valid else []
    return [
        PressureObservation("1.0", session_id, sample.timestamp_ms, "legacy_sample_timestamp", sensor_id,
                            channel, raw, raw if sample.valid else None, CalibrationState(status),
                            GridPosition(None, column), flags)
        for channel, raw, column in (("left_legacy", sample.left_force_n, 0),
                                     ("right_legacy", sample.right_force_n, 1))
    ]


def from_current_analysis(value: Any) -> SessionResult:
    """Loss-aware adapter for one legacy AnalysisResult packet, which is not a full session report."""
    packet = value.to_dict() if hasattr(value, "to_dict") else value
    decision = packet["decision"]
    unavailable = bool(decision.get("abstained"))
    assessment = AssessmentResult(
        "legacy_primary_cue", "unavailable" if unavailable else
        ("adequate" if not decision.get("reason") else "condition_detected"),
        decision.get("confidence"), decision.get("reason") or ("legacy_packet_abstained" if unavailable else None),
        packet.get("rep_id"), "multimodal",
    )
    interval = RepetitionInterval(packet["rep_id"], packet["timestamp_ms"], None, packet["timestamp_ms"], None)
    measurements = packet.get("measurements", {})
    pressure_features = {name: measurements[name] for name in
                         ("left_force_n", "right_force_n", "asymmetry_percent") if name in measurements} or None
    return SessionResult("1.0", packet["session_id"], "multimodal", packet["rep_id"], [interval],
                         ViewpointEstimate("unknown"), [assessment], pressure_features,
                         SynchronizationReport("unavailable", reason="legacy_packet_has_no_sync_report"),
                         0.0 if unavailable else 1.0, ["adapted_from_single_legacy_analysis_packet"],
                         [assessment] if unavailable else [])
