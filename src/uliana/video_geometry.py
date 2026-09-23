from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Landmark:
    x: float
    y: float
    z: float = 0.0
    visibility: float = 0.0
    presence: float = 0.0

    @property
    def quality(self) -> float:
        return min(self.visibility, self.presence)


SIDES = {
    "left": ("left_shoulder", "left_elbow", "left_wrist", "left_hip", "left_ankle"),
    "right": ("right_shoulder", "right_elbow", "right_wrist", "right_hip", "right_ankle"),
}


def _xy(point: Landmark, width: int, height: int) -> tuple[float, float]:
    return point.x * width, point.y * height


def image_plane_angle(a: Landmark, vertex: Landmark, c: Landmark, width: int, height: int) -> float:
    """Angle in pixel-scaled image plane; normalized x/y are aspect-ratio corrected."""
    ax, ay = _xy(a, width, height); bx, by = _xy(vertex, width, height); cx, cy = _xy(c, width, height)
    u, v = (ax - bx, ay - by), (cx - bx, cy - by)
    denominator = math.hypot(*u) * math.hypot(*v)
    if denominator <= 1e-9:
        raise ValueError("coincident landmarks cannot define an angle")
    return math.degrees(math.acos(max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / denominator))))


def body_line_deviation(shoulder: Landmark, hip: Landmark, ankle: Landmark, width: int, height: int) -> float:
    """Deviation from a straight shoulder-hip-ankle line: abs(180° - image-plane angle)."""
    return abs(180.0 - image_plane_angle(shoulder, hip, ankle, width, height))


def side_quality(landmarks: dict[str, Landmark], side: str) -> float | None:
    required = SIDES[side]
    if any(name not in landmarks for name in required):
        return None
    return min(landmarks[name].quality for name in required)


def choose_visible_side(frames: list[dict[str, Landmark]], minimum_margin: float = 0.05) -> tuple[str | None, str]:
    """Choose once per clip from calibration frames; never switch side frame-to-frame."""
    means = {}
    for side in SIDES:
        values = [value for frame in frames if (value := side_quality(frame, side)) is not None]
        means[side] = sum(values) / len(values) if values else None
    if means["left"] is None and means["right"] is None:
        return None, "required_landmarks_missing"
    if means["right"] is None or (means["left"] is not None and means["left"] > means["right"] + minimum_margin):
        return "left", "higher_calibration_quality"
    if means["left"] is None or means["right"] > means["left"] + minimum_margin:
        return "right", "higher_calibration_quality"
    return "left", "quality_tie_anatomical_left_default"


def geometry_for_side(landmarks: dict[str, Landmark], side: str, width: int, height: int, minimum_quality: float) -> tuple[float | None, float | None, float, str | None]:
    quality = side_quality(landmarks, side)
    if quality is None:
        return None, None, 0.0, "required_landmarks_missing"
    shoulder, elbow, wrist, hip, ankle = (landmarks[name] for name in SIDES[side])
    try:
        elbow_angle = image_plane_angle(shoulder, elbow, wrist, width, height)
        body_error = body_line_deviation(shoulder, hip, ankle, width, height)
        reason = "required_landmarks_low_quality" if quality < minimum_quality else None
        return elbow_angle, body_error, quality, reason
    except ValueError:
        return None, None, quality, "degenerate_landmark_geometry"
