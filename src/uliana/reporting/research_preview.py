"""Post-process frozen camera intervals into non-headline research observations.

This module deliberately runs after ``video.camera_session`` has produced its
frozen repetition count and supported assessments.  Its output is serialized
separately and must never be merged into SessionResult.assessments, coverage,
review counts, progress statistics, or corrective-cue selection.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from uliana.contracts.models import RepetitionInterval, VideoObservation
from uliana.fusion.criteria_v2 import (
    assess_elbow_to_torso_flare,
    assess_hand_placement,
    assess_head_neck_alignment,
)
from uliana.video.criterion_geometry import _extract_head_neck_data, _usable


@dataclass(frozen=True)
class ResearchPreviewFeatures:
    rep_id: int
    viewpoint: str
    viewpoint_confidence: float | None
    valid_frame_fraction: float
    frame_count: int
    head_neck_data: list[tuple[int, float, float]] | None
    hand_placement_data: list[tuple[int, float, float, float]] | None
    elbow_flare_data: list[tuple[int, float, float]] | None


def _hand_placement(frames: list[VideoObservation], config: dict):
    values = []
    for frame in frames:
        names = ("left_wrist", "right_wrist", "left_shoulder", "right_shoulder")
        if not _usable(frame, names, config):
            continue
        lm = frame.pose.landmarks
        width = abs(lm["left_shoulder"].x - lm["right_shoulder"].x)
        if width * frame.image_width_px <= 1:
            continue
        midpoint = (lm["left_shoulder"].x + lm["right_shoulder"].x) / 2
        left = (lm["left_wrist"].x - lm["left_shoulder"].x) / (lm["left_shoulder"].x - lm["right_shoulder"].x)
        right = (lm["right_wrist"].x - lm["right_shoulder"].x) / (lm["right_shoulder"].x - lm["left_shoulder"].x)
        values.append((frame.timestamp_ms, left, right, midpoint))
    return values or None


def _flare_angle(shoulder, elbow, shoulder_mid_x, shoulder_mid_y, hip_mid, width, height):
    if hip_mid is None:
        return None
    arm = ((elbow.x - shoulder.x) * width, (elbow.y - shoulder.y) * height)
    torso = ((hip_mid[0] - shoulder_mid_x) * width, (hip_mid[1] - shoulder_mid_y) * height)
    denominator = math.hypot(*arm) * math.hypot(*torso)
    if denominator <= 1e-9:
        return None
    cosine = max(-1.0, min(1.0, (arm[0] * torso[0] + arm[1] * torso[1]) / denominator))
    if abs(cosine - 1.0) < 1e-12:
        return 0.0
    return math.degrees(math.acos(cosine))


def _elbow_flare(frames: list[VideoObservation], config: dict):
    values = []
    names = ("left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_hip", "right_hip")
    for frame in frames:
        if not _usable(frame, names, config):
            continue
        lm = frame.pose.landmarks
        shoulder_mid = ((lm["left_shoulder"].x + lm["right_shoulder"].x) / 2, (lm["left_shoulder"].y + lm["right_shoulder"].y) / 2)
        hip_mid = ((lm["left_hip"].x + lm["right_hip"].x) / 2, (lm["left_hip"].y + lm["right_hip"].y) / 2)
        left = _flare_angle(lm["left_shoulder"], lm["left_elbow"], *shoulder_mid, hip_mid, frame.image_width_px, frame.image_height_px)
        right = _flare_angle(lm["right_shoulder"], lm["right_elbow"], *shoulder_mid, hip_mid, frame.image_width_px, frame.image_height_px)
        if left is not None and right is not None:
            values.append((frame.timestamp_ms, left, right))
    return values or None


def extract_research_features(
    observations: list[VideoObservation],
    interval: RepetitionInterval,
    observable_side: str,
    viewpoint: str,
    viewpoint_confidence: float | None,
    config: dict,
) -> ResearchPreviewFeatures:
    frames = [item for item in observations if interval.start_ms <= item.timestamp_ms <= interval.end_ms]
    return ResearchPreviewFeatures(
        rep_id=interval.rep_id,
        viewpoint=viewpoint,
        viewpoint_confidence=viewpoint_confidence,
        valid_frame_fraction=sum(frame.pose.detected for frame in frames) / len(frames) if frames else 0,
        frame_count=len(frames),
        head_neck_data=_extract_head_neck_data(frames, observable_side, config),
        hand_placement_data=_hand_placement(frames, config),
        elbow_flare_data=_elbow_flare(frames, config),
    )


def build_research_preview(
    observations: list[VideoObservation],
    intervals: list[RepetitionInterval],
    observable_side: str,
    viewpoint: str,
    viewpoint_confidence: float | None,
    config: dict,
) -> dict:
    """Return separately serialized experimental observations for frozen reps."""
    assessments = []
    feature_rows = []
    for interval in intervals:
        features = extract_research_features(observations, interval, observable_side, viewpoint, viewpoint_confidence, config)
        feature_rows.append(asdict(features))
        confidence = interval.confidence or 0
        assessments.extend((
            assess_head_neck_alignment(features, confidence, config),
            assess_elbow_to_torso_flare(features, confidence, config),
            assess_hand_placement(features, confidence, config),
        ))
    return {
        "schema_version": "1.0",
        "validation_status": "experimental-trainer-validation-pending",
        "excluded_from": ["primary_feedback", "review_count", "progress", "frozen_evaluation"],
        "features": feature_rows,
        "assessments": [item.to_dict() for item in assessments],
    }
