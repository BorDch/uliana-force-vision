from __future__ import annotations

import math

from uliana.contracts.models import LandmarkObservation


def pixel_distance(a: LandmarkObservation, b: LandmarkObservation, width: int, height: int) -> float:
    return math.hypot((a.x - b.x) * width, (a.y - b.y) * height)


def midpoint(a: LandmarkObservation, b: LandmarkObservation) -> tuple[float, float]:
    return (a.x + b.x) / 2, (a.y + b.y) / 2


def torso_length(landmarks: dict[str, LandmarkObservation], width: int, height: int) -> float | None:
    required = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
    if any(name not in landmarks for name in required): return None
    shoulders = midpoint(landmarks["left_shoulder"], landmarks["right_shoulder"])
    hips = midpoint(landmarks["left_hip"], landmarks["right_hip"])
    return math.hypot((shoulders[0] - hips[0]) * width, (shoulders[1] - hips[1]) * height)


def axis_angle(a: LandmarkObservation, b: LandmarkObservation, width: int, height: int) -> float:
    return math.degrees(math.atan2((b.y-a.y)*height, (b.x-a.x)*width))
