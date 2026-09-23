import pytest
from dataclasses import replace

from test_camera_milestone4 import CONFIG, cycle, summary
from uliana.contracts.models import LandmarkObservation, RepetitionInterval
from uliana.video.camera_session import analyze_camera_observations
from uliana.fusion import assess_hand_placement, assess_head_neck_alignment, assess_elbow_to_torso_flare
from uliana.reporting.feedback_policy import compose_feedback
from uliana.reporting.research_preview import build_research_preview, extract_research_features, _flare_angle


def features(offset=0, quality=1, view="front"):
    frames = []
    for frame in cycle(view):
        lm = dict(frame.pose.landmarks)
        for side, x, sign in (("left", .3, -1), ("right", .7, 1)):
            lm[side+"_shoulder"] = LandmarkObservation(x, .3, 0, 1, 1)
            lm[side+"_wrist"] = LandmarkObservation(x+sign*offset*.4, .7, 0, quality, quality)
            lm[side+"_hip"] = LandmarkObservation(x, .6, 0, 1, 1)
            lm[side+"_ear"] = LandmarkObservation(x, .2, 0, 1, 1)
        frames.append(replace(frame, pose=replace(frame.pose, landmarks=lm)))
    return extract_research_features(frames, RepetitionInterval(1, 0, 400, 800, .9), "left", view, .9, CONFIG)


@pytest.mark.parametrize("offset,expected", [(0,"adequate"),(.5,"condition_detected"),(-.5,"condition_detected")])
def test_hand_position_from_corresponding_shoulder(offset, expected):
    item = features(offset)
    check = assess_hand_placement(item, .9, CONFIG)
    assert check.result == expected
    assert check.evidence["maximum_wrist_offset"] == pytest.approx(abs(offset))


def test_low_quality_wrists_and_sparse_coverage_abstain():
    assert assess_hand_placement(features(quality=.1), .9, CONFIG).result == "unavailable"
    item = features()
    assert assess_hand_placement(replace(item,hand_placement_data=item.hand_placement_data[:2]),.9,CONFIG).result == "unavailable"


def test_side_hands_and_flare_abstain_even_with_landmarks():
    item = features(view="side")
    assert assess_hand_placement(item,.9,CONFIG).reason == "viewpoint_not_supported"
    assert assess_elbow_to_torso_flare(item,.9,CONFIG).reason == "viewpoint_not_supported"


def test_head_line_and_deviation():
    item = features(view="side")
    assert assess_head_neck_alignment(item,.9,CONFIG).result == "adequate"
    bad = replace(item,head_neck_data=[(t,.3,y) for t,_,y in item.head_neck_data])
    assert assess_head_neck_alignment(bad,.9,CONFIG).result == "condition_detected"
    assert assess_head_neck_alignment(replace(item,viewpoint="front"),.9,CONFIG).result == "unavailable"


def test_flare_uses_same_pixel_coordinates_for_arm_and_torso():
    shoulder=LandmarkObservation(.3,.3)
    elbow=LandmarkObservation(.4,.4)
    assert _flare_angle(shoulder,elbow,.3,.3,(.5,.5),200,100) == pytest.approx(0,abs=1e-6)


def test_frozen_pipeline_emits_two_supported_checks_and_postprocessor_emits_research_preview():
    result,_,_,metrics = analyze_camera_observations(cycle(),summary(),CONFIG)
    preview = build_research_preview(cycle(), result.repetition_intervals, "left", result.detected_viewpoint.value, result.detected_viewpoint.confidence, CONFIG)
    report = compose_feedback(result.to_dict(),metrics,preview)
    supported={"body_alignment_deviation","push_up_depth_proxy"}
    experimental={"head_neck_alignment","elbow_to_torso_flare","hand_placement"}
    assert {a.condition for a in result.assessments} == supported
    assert {a["condition"] for a in preview["assessments"]} == experimental
    assert {a["criterion_id"] for a in report["criterion_cards"]} == supported | experimental
    assert len(report["criterion_cards"]) == 5 * result.repetition_count


def test_hand_feedback_displays_threshold_not_measurement():
    check=assess_hand_placement(features(.5),.9,CONFIG)
    report=compose_feedback({"repetition_count":1,"assessments":[check.to_dict()]})
    assert report["criterion_cards"][0]["threshold"] == .3
    assert report["primary_observation"]["criterion_id"] == "recording_quality"
    assert report["criterion_cards"][0]["validation_status"].startswith("experimental")
