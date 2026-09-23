import json
from pathlib import Path

import pytest

from uliana.config import load_config
from uliana.contracts.models import LandmarkObservation, PoseObservation, VideoObservation, ViewpointEstimate
from uliana.contracts.validation import validate_contract
from uliana.video.landmark_quality import assess_landmark_quality
from uliana.video.pose_estimator import MediaPipeObservationAdapter
from uliana.video.smoothing import LandmarkSmoother
from uliana.video.viewpoint import ViewpointFrameEvidence, ViewpointTracker, classify_viewpoint, summarize_viewpoints

CONFIG = load_config(Path(__file__).parents[1] / "configs/video_processing.json")


def point(x, y, visibility=1, presence=1, z=0):
    return LandmarkObservation(x, y, z, visibility, presence)


def observation(shoulder_dx, hip_dx=None, left_quality=1, right_quality=1, timestamp=0, extra=None):
    hip_dx = shoulder_dx if hip_dx is None else hip_dx
    landmarks = {
        "left_shoulder": point(.5-shoulder_dx/2, .3, left_quality, left_quality),
        "right_shoulder": point(.5+shoulder_dx/2, .3, right_quality, right_quality),
        "left_hip": point(.5-hip_dx/2, .6, left_quality, left_quality),
        "right_hip": point(.5+hip_dx/2, .6, right_quality, right_quality),
        "left_elbow": point(.4, .45, left_quality, left_quality), "right_elbow": point(.6, .45, right_quality, right_quality),
        "left_wrist": point(.35, .65, left_quality, left_quality), "right_wrist": point(.65, .65, right_quality, right_quality),
        "left_ankle": point(.45, .9, left_quality, left_quality), "right_ankle": point(.55, .9, right_quality, right_quality),
        "nose": point(.5, .15), "left_ear": point(.47, .16), "right_ear": point(.53, .16),
    }
    landmarks.update(extra or {})
    return VideoObservation("1.0", "s", timestamp//33, timestamp, "synthetic", 30, 640, 480,
        PoseObservation(True, landmarks, .9, landmarks.copy()), ViewpointEstimate("unknown"), [])


@pytest.mark.parametrize("value,expected", [
    (observation(.03, left_quality=1, right_quality=.6), "side"),
    (observation(.4, left_quality=.95, right_quality=.94), "front"),
    (observation(.15, left_quality=.95, right_quality=.84), "oblique"),
])
def test_clear_geometric_viewpoints(value, expected):
    assert classify_viewpoint(value, CONFIG).label == expected


def test_ambiguous_and_conflicting_viewpoints_are_unknown():
    assert classify_viewpoint(observation(.03), CONFIG).label == "unknown"
    assert classify_viewpoint(observation(.4, left_quality=1, right_quality=.5), CONFIG).label == "unknown"


def test_quality_codes_are_condition_specific_and_detect_frame_edge():
    value = observation(.4, extra={"left_wrist": point(.001, .6, visibility=.2, presence=.9)})
    quality = assess_landmark_quality(value, CONFIG)
    assert {"low_visibility", "likely_occlusion", "partial_body_out_of_frame"} <= set(quality.codes)
    assert quality.group_available["shoulders"] and not quality.group_available["wrists"]


def test_session_side_selection_is_fixed_by_aggregation():
    evidence = [classify_viewpoint(observation(.03, left_quality=1, right_quality=.6, timestamp=t), CONFIG) for t in range(0, 1000, 100)]
    result = summarize_viewpoints(evidence, CONFIG)
    assert result["viewpoint"].value == "side" and result["observable_side"] == "left"


def test_viewpoint_hysteresis_and_change_after_dwell():
    tracker = ViewpointTracker(500)
    def ev(t, label): return ViewpointFrameEvidence(t, label, .9, "synthetic", {}, "ambiguous")
    assert tracker.update(ev(0, "side")) == "unknown"
    assert tracker.update(ev(300, "side")) == "unknown"
    assert tracker.update(ev(500, "side")) == "side"
    assert tracker.update(ev(600, "front")) == "side"
    assert tracker.update(ev(1100, "front")) == "front"
    assert len(tracker.changes) == 2


def test_smoothing_reduces_jitter_and_uses_irregular_timestamps():
    smoother = LandmarkSmoother(CONFIG); raw=[]; smoothed=[]
    for index, timestamp in enumerate((0, 20, 55, 90, 140, 205)):
        x=.4 + (.02 if index%2 else -.02); value=observation(.2, timestamp=timestamp, extra={"left_wrist":point(x,.65)})
        raw.append(x); smoothed.append(smoother.process(value).pose.landmarks["left_wrist"].x)
    raw_variation=sum(abs(b-a) for a,b in zip(raw,raw[1:])); smooth_variation=sum(abs(b-a) for a,b in zip(smoothed,smoothed[1:]))
    assert smooth_variation < raw_variation


def test_filter_resets_after_pose_gap_without_bridging():
    smoother=LandmarkSmoother(CONFIG)
    smoother.process(observation(.2,timestamp=0,extra={"left_wrist":point(.2,.65)}))
    value=smoother.process(observation(.2,timestamp=500,extra={"left_wrist":point(.8,.65)}))
    assert value.pose.landmarks["left_wrist"].x == .8
    assert "excessive_pose_gap" in value.quality_flags


def test_stable_video_observation_serialization_and_world_caveat():
    value=observation(.4)
    validate_contract("video_observation",value)
    json.dumps(value.to_dict(),allow_nan=False)


def test_mediapipe_adapter_is_lazy(tmp_path):
    with pytest.raises(FileNotFoundError):
        MediaPipeObservationAdapter(tmp_path/"missing.task")
