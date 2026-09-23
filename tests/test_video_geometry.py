import pytest

from uliana.video_geometry import Landmark, body_line_deviation, choose_visible_side, geometry_for_side, image_plane_angle


def point(px, py, width, height, quality=1):
    return Landmark(px / width, py / height, visibility=quality, presence=quality)


def test_image_plane_geometry_is_aspect_ratio_corrected():
    a = image_plane_angle(point(0, 50, 200, 100), point(100, 50, 200, 100), point(100, 100, 200, 100), 200, 100)
    assert a == pytest.approx(90)
    assert body_line_deviation(point(0, 50, 200, 100), point(100, 50, 200, 100), point(200, 50, 200, 100), 200, 100) == pytest.approx(0)


def test_visible_side_is_locked_from_calibration_quality():
    frame = {}
    for joint in ("shoulder", "elbow", "wrist", "hip", "ankle"):
        frame[f"left_{joint}"] = Landmark(.2, .2, visibility=.9, presence=.9)
        frame[f"right_{joint}"] = Landmark(.8, .2, visibility=.5, presence=.5)
    assert choose_visible_side([frame])[0] == "left"


def test_low_quality_landmark_preserves_diagnostic_geometry():
    landmarks = {
        "right_shoulder": point(0, 50, 200, 100),
        "right_elbow": point(100, 50, 200, 100),
        "right_wrist": point(100, 100, 200, 100),
        "right_hip": point(100, 50, 200, 100),
        "right_ankle": point(200, 50, 200, 100, quality=.2),
    }
    elbow, body, quality, reason = geometry_for_side(landmarks, "right", 200, 100, .65)
    assert elbow == pytest.approx(90) and body == pytest.approx(0)
    assert quality == pytest.approx(.2) and reason == "required_landmarks_low_quality"
