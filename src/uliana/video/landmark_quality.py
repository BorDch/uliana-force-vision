from __future__ import annotations

from dataclasses import dataclass

from uliana.contracts.models import LandmarkObservation, VideoObservation
from .geometry import pixel_distance, torso_length


@dataclass(frozen=True)
class FrameQuality:
    codes: list[str]
    group_available: dict[str, bool]
    usable_for_phase: bool
    torso_scale_px: float | None


def assess_landmark_quality(observation: VideoObservation, config: dict,
                            previous: VideoObservation | None = None, previous_scale: float | None = None) -> FrameQuality:
    pose, limits = observation.pose, config["landmark_quality"]
    if not pose.detected:
        return FrameQuality(["pose_not_detected"], {name: False for name in limits["groups"]}, False, None)
    landmarks = pose.landmarks; codes = []; groups = {}
    for group, names in limits["groups"].items():
        missing = [name for name in names if name not in landmarks]
        low_visibility = [name for name in names if name in landmarks and (landmarks[name].visibility or 0) < limits["minimum_visibility"]]
        low_presence = [name for name in names if name in landmarks and (landmarks[name].presence or 0) < limits["minimum_presence"]]
        groups[group] = not missing and not low_visibility and not low_presence
        if missing and "required_landmark_missing" not in codes: codes.append("required_landmark_missing")
        if low_visibility and "low_visibility" not in codes: codes.append("low_visibility")
        if low_presence and "low_presence" not in codes: codes.append("low_presence")
        if any(name in landmarks and (landmarks[name].visibility or 0) < limits["minimum_visibility"] and
               (landmarks[name].presence or 0) >= limits["minimum_presence"] for name in names) and "likely_occlusion" not in codes:
            codes.append("likely_occlusion")
    margin = limits["frame_margin"]
    if any(point.x < margin or point.x > 1-margin or point.y < margin or point.y > 1-margin for point in landmarks.values()):
        codes.append("partial_body_out_of_frame")
    scale = torso_length(landmarks, observation.image_width_px, observation.image_height_px)
    if scale and previous_scale and abs(scale-previous_scale)/previous_scale > limits["maximum_scale_change_fraction"]:
        codes.append("inconsistent_person_scale")
    if previous and observation.timestamp_ms - previous.timestamp_ms > config["maximum_pose_gap_ms"]:
        codes.append("excessive_pose_gap")
    if previous and scale:
        shared = set(landmarks) & set(previous.pose.landmarks)
        if any(pixel_distance(landmarks[name], previous.pose.landmarks[name], observation.image_width_px,
                              observation.image_height_px) / scale > limits["maximum_landmark_jump_torso_lengths"] for name in shared):
            codes.append("implausible_landmark_jump")
    usable = groups.get("elbows", False) and groups.get("shoulders", False) and groups.get("wrists", False)
    return FrameQuality(codes, groups, usable, scale)
