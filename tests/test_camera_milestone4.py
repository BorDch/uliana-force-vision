import math
from dataclasses import replace
from pathlib import Path

import pytest

from uliana.config import load_config
from uliana.contracts.models import LandmarkObservation,PoseObservation,VideoObservation,ViewpointEstimate
from uliana.contracts.validation import validate_contract
from uliana.fusion.assessments import assess_body_alignment,assess_depth_proxy
from uliana.video.camera_session import analyze_camera_observations
from uliana.video.features import RepetitionCameraFeatures,extract_repetition_features
from uliana.video.phases import segment_repetitions, select_phase_signal

CONFIG=load_config(Path(__file__).parents[1]/"configs/video_processing.json")


def frame(timestamp,angle,view="side",side="left",hip_offset=0,detected=True):
    elbow=(.55,.45);wrist=(.72,.45);length=.18;theta=math.radians(angle)
    shoulder=(elbow[0]+length*math.cos(theta),elbow[1]+length*math.sin(theta));ankle=(.12,.62)
    hip=((shoulder[0]+ankle[0])/2+hip_offset,(shoulder[1]+ankle[1])/2)
    def p(xy,q=1):return LandmarkObservation(xy[0],xy[1],0,q,q)
    lm={}
    for prefix,shift in (("left",0),("right",.02)):
        lm[f"{prefix}_shoulder"]=p((shoulder[0]+shift,shoulder[1]));lm[f"{prefix}_elbow"]=p((elbow[0]+shift,elbow[1]));lm[f"{prefix}_wrist"]=p((wrist[0]+shift,wrist[1]));lm[f"{prefix}_hip"]=p((hip[0]+shift,hip[1]));lm[f"{prefix}_ankle"]=p((ankle[0]+shift,ankle[1]))
    return VideoObservation("1.0","session",timestamp//50,timestamp,"synthetic",20,100,100,
        PoseObservation(detected,lm if detected else {},.9,lm if detected else {}),ViewpointEstimate(view,.9,"synthetic"),[])


def cycle(view="side",minimum=95,hip_offsets=None,start=0):
    angles=[165,165,165,145,145,125,minimum,minimum,minimum,125,125,145,165,165,165,165,165]
    offsets=hip_offsets or [0]*len(angles)
    return [frame(start+i*50,angle,view,hip_offset=offsets[i]) for i,angle in enumerate(angles)]


def summary(view="side",confidence=.9,side="left"):
    return {"dominant_viewpoint":{"value":view,"confidence":confidence,"reason":"synthetic"},
        "observable_anatomical_side":side,"viewpoint_changes":[],"warnings":[]}


def test_complete_side_rep_and_left_right_selection():
    left=segment_repetitions(cycle(),"side","left",CONFIG);right=segment_repetitions(cycle(),"side","right",CONFIG)
    assert len(left.intervals)==1 and left.selected_signal.name=="observable_elbow_angle"
    assert len(right.intervals)==1 and right.selected_signal.name=="observable_elbow_angle"
    assert left.intervals[0].bottom_ms is not None


def test_threshold_jitter_does_not_double_count_and_incomplete_is_discarded():
    jitter=[frame(i*50,a) for i,a in enumerate([165,165,145,150,144,130,95,95,130,149,151,165,165])]
    assert len(segment_repetitions(jitter,"side","left",CONFIG).intervals)<=1
    incomplete=[frame(i*50,a) for i,a in enumerate([165,165,165,145,145,125,95,95,95,120])]
    result=segment_repetitions(incomplete,"side","left",CONFIG)
    assert not result.intervals and "incomplete_repetition_discarded" in result.warnings


def test_pose_gap_and_viewpoint_change_reset():
    first=cycle()[:6];second=[replace(item,timestamp_ms=item.timestamp_ms+500,frame_index=item.frame_index+10) for item in cycle()[6:]]
    assert not segment_repetitions(first+second,"side","left",CONFIG).intervals
    observations=cycle()+[replace(item,timestamp_ms=item.timestamp_ms+600,frame_index=item.frame_index+20,viewpoint=ViewpointEstimate("front",.9,"change")) for item in cycle("front")]
    video_summary=summary("side");video_summary["viewpoint_changes"]=[{"timestamp_ms":600,"from":"side","to":"front"}]
    result,_,_,_=analyze_camera_observations(observations,video_summary,CONFIG)
    assert "viewpoint_change_reset_phase_state" in result.warnings


def test_insufficient_samples_and_nearly_constant_signal_abstain():
    insufficient=cycle()[:6]+[frame(300+i*50,165,detected=False) for i in range(6)]
    assert select_phase_signal(insufficient,"side","left",CONFIG) is None
    nearly_constant=[frame(i*50,165-(i%3)) for i in range(20)]
    assert select_phase_signal(nearly_constant,"side","left",CONFIG) is None


def test_single_excursion_is_not_split_into_multiple_repetitions():
    excursion=[frame(i*50,a) for i,a in enumerate([165,165,165,145,130,95,95,95,130,145,165,165,165,164,165])]
    assert len(segment_repetitions(excursion,"side","left",CONFIG).intervals)==1


def test_front_bilateral_count_but_conditions_unavailable():
    observations=cycle("front");result,_,_,metrics=analyze_camera_observations(observations,summary("front",side="ambiguous"),CONFIG)
    assert result.repetition_count==1 and result.provenance["phase_signal"]=="bilateral_elbow_angle"
    checks = {item.condition: item for item in result.assessments}
    for name in ("body_alignment_deviation", "push_up_depth_proxy"):
        assert checks[name].reason == "viewpoint_not_supported"
    assert set(checks) == {"body_alignment_deviation", "push_up_depth_proxy"}
    assert metrics["eligible_assessments"] == 2


def test_front_low_amplitude_and_unknown_abstain_from_count():
    weak=[frame(i*50,a,"front") for i,a in enumerate([165,164,163,164,165,164])]
    result,_,_,_=analyze_camera_observations(weak,summary("front",side="ambiguous"),CONFIG)
    assert result.repetition_count is None
    unknown=[replace(item,viewpoint=ViewpointEstimate("unknown",.2,"weak")) for item in weak]
    result,_,_,_=analyze_camera_observations(unknown,summary("unknown",.2,"ambiguous"),CONFIG)
    assert result.repetition_count is None


def test_oblique_strict_gate_can_count_or_abstain():
    result,_,_,_=analyze_camera_observations(cycle("oblique"),summary("oblique",.75),CONFIG)
    assert result.repetition_count==1
    weak=[frame(i*50,a,"oblique") for i,a in enumerate([165,160,158,160,165])]
    result,_,_,_=analyze_camera_observations(weak,summary("oblique",.75),CONFIG)
    assert result.repetition_count is None


def _features(observations,hip=False):
    segmented=segment_repetitions(observations,"side","left",CONFIG);assert segmented.intervals
    return extract_repetition_features(observations,segmented.intervals[0],"left",CONFIG),segmented.intervals[0].confidence


def test_persistent_alignment_one_frame_outlier_and_adequate():
    persistent=[.08]*len(cycle())
    features,confidence=_features(cycle(hip_offsets=persistent));assessment=assess_body_alignment(replace(features,viewpoint_confidence=.9),confidence,CONFIG)
    assert assessment.result=="condition_detected"
    outlier=[0]*len(cycle());outlier[7]=.08
    features,confidence=_features(cycle(hip_offsets=outlier));assessment=assess_body_alignment(replace(features,viewpoint_confidence=.9),confidence,CONFIG)
    assert assessment.result=="adequate"
    features,confidence=_features(cycle());assert assess_body_alignment(replace(features,viewpoint_confidence=.9),confidence,CONFIG).result=="adequate"


def test_insufficient_alignment_landmarks_is_unavailable():
    features,confidence=_features(cycle());features=replace(features,alignment_angle_deviation_deg=[],normalized_hip_displacement=[],signed_hip_displacement=[],viewpoint_confidence=.9)
    assert assess_body_alignment(features,confidence,CONFIG).reason=="required_landmarks_unavailable"


def test_depth_adequate_insufficient_range_and_unreliable_bottom():
    features,confidence=_features(cycle(minimum=95));features=replace(features,viewpoint_confidence=.9)
    assert assess_depth_proxy(features,confidence,CONFIG).result=="adequate"
    features,confidence=_features(cycle(minimum=125));features=replace(features,viewpoint_confidence=.9)
    assessment=assess_depth_proxy(features,confidence,CONFIG);assert assessment.result=="condition_detected" and assessment.reason=="insufficient_range_of_motion"
    assert assess_depth_proxy(replace(features,bottom_ms=None),confidence,CONFIG).reason=="phase_detection_unreliable"


def test_independent_availability_coverage_and_schema():
    observations=cycle();result,_,_,metrics=analyze_camera_observations(observations,summary(),CONFIG)
    validate_contract("session_result",result)
    assert result.repetition_count==1 and len(result.assessments)==2
    assert metrics["eligible_assessments"]==2 and 0<=result.overall_assessment_coverage<=1
