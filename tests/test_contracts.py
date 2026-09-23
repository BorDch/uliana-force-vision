import pytest

from uliana.contracts import (
    AssessmentResult, CalibrationState, GridPosition, PoseObservation, PressureObservation,
    SessionResult, SynchronizationReport, VideoObservation, ViewpointEstimate,
    from_force_sample, from_pose_frame, validate_contract,
)
from uliana.contracts.validation import ContractValidationError
from uliana.pose_adapter import PoseFrame
from uliana.types import ForceSample
from uliana.types import AnalysisResult
from uliana.video_geometry import Landmark


def camera_result(viewpoint="unknown"):
    return SessionResult("1.0", "s1", "camera_only", 0, [], ViewpointEstimate(viewpoint),
                         [AssessmentResult("depth", "unavailable", None, "viewpoint_unknown", modality="camera")],
                         None, SynchronizationReport("not_applicable"), 0.0, [],
                         [AssessmentResult("depth", "unavailable", None, "viewpoint_unknown", modality="camera")])


def test_camera_only_unknown_viewpoint_and_unavailable_reason_are_valid():
    validate_contract("session_result", camera_result())


def test_pressure_only_and_multimodal_modes_are_valid():
    for mode in ("pressure_only", "multimodal"):
        value = camera_result().to_dict(); value["mode"] = mode
        value["synchronization"]["status"] = "unavailable" if mode == "multimodal" else "not_applicable"
        validate_contract("session_result", value)


def test_arbitrary_four_cell_mat_and_nullable_uncalibrated_force():
    for row in range(2):
        for column in range(2):
            observation = PressureObservation("1.0", "s1", 0, "device_clock", "mat", f"cell_{row}{column}",
                100, None, CalibrationState("uncalibrated"), GridPosition(row, column))
            validate_contract("pressure_observation", observation)


def test_invalid_enum_and_unavailable_without_reason_are_rejected():
    bad = camera_result().to_dict(); bad["detected_viewpoint"]["value"] = "360_degree"
    with pytest.raises(ContractValidationError): validate_contract("session_result", bad)
    bad = camera_result().to_dict(); bad["assessments"][0]["reason"] = None
    with pytest.raises(ContractValidationError): validate_contract("session_result", bad)


def test_legacy_pose_frame_and_force_sample_conversion():
    frame = PoseFrame(2, 40, "container_timestamp", True, {"left_wrist": Landmark(.2, .3, visibility=.9, presence=.8)}, 4)
    video = from_pose_frame(frame, "s1", 30, 640, 480)
    validate_contract("video_observation", video)
    pressure = from_force_sample(ForceSample(40, 10, 12), "s1")
    assert [item.channel_id for item in pressure] == ["left_legacy", "right_legacy"]
    for item in pressure: validate_contract("pressure_observation", item)


def test_video_contract_rejects_invalid_viewpoint():
    video = VideoObservation("1.0", "s1", 0, 0, "container", 30, 640, 480,
                             PoseObservation(False), ViewpointEstimate("unknown"), ["pose_not_detected"])
    validate_contract("video_observation", video)


def test_legacy_analysis_packet_conversion():
    packet = AnalysisResult("1.0", "toy_simulator", "s1", 100, 1, "up",
        {"left_force_n": 10, "right_force_n": 11, "asymmetry_percent": 4, "elbow_angle_deg": 90,
         "body_line_error_deg": 2}, {"overall": 90, "balance": 90, "depth": 90, "alignment": 90},
        {"cue": "Good repetition.", "confidence": .9, "abstained": False, "reason": None})
    from uliana.contracts import from_current_analysis
    result = from_current_analysis(packet)
    assert "elbow_angle_deg" not in result.pressure_features
    validate_contract("session_result", result)
