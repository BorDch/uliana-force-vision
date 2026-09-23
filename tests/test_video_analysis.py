import json
from pathlib import Path

from jsonschema import validate

from uliana.pose_adapter import PoseFrame
from uliana.video_analysis import analyze_pose_frames, replay_packets
from uliana.video_geometry import Landmark


def landmarks_for_angle(angle_hint, quality=1):
    # Geometry is intentionally controlled through shoulder vertical displacement.
    shoulder_y = {165: .52, 140: .45, 120: .36, 90: .25}.get(angle_hint, .52)
    return {
        "left_shoulder": Landmark(.4, shoulder_y, visibility=quality, presence=quality),
        "left_elbow": Landmark(.5, .5, visibility=quality, presence=quality),
        "left_wrist": Landmark(.65, .5, visibility=quality, presence=quality),
        "left_hip": Landmark(.3, shoulder_y, visibility=quality, presence=quality),
        "left_ankle": Landmark(.15, shoulder_y, visibility=quality, presence=quality),
    }


def test_missing_pose_is_unavailable_and_does_not_complete_rep(config):
    real_config = json.loads((Path(__file__).parents[1] / "configs" / "real_video.json").read_text())
    frames = [PoseFrame(0, 0, "container_timestamp", True, landmarks_for_angle(165), 1),
              PoseFrame(1, 100, "container_timestamp", True, landmarks_for_angle(90), 1),
              PoseFrame(2, 500, "container_timestamp", False, {}, 1),
              PoseFrame(3, 600, "container_timestamp", True, landmarks_for_angle(165), 1)]
    diagnostics, repetitions, _, _ = analyze_pose_frames(frames, 200, 100, real_config)
    assert diagnostics[2]["reliability_reason"] == "pose_not_detected"
    assert repetitions == []


def test_simulated_force_replay_is_schema_compatible():
    real_config = json.loads((Path(__file__).parents[1] / "configs" / "real_video.json").read_text())
    from uliana.video_analysis import VideoRepetition
    repetition = VideoRepetition(1, 0, 500, 1000, 95, 3, .9, "Good repetition.", False, None)
    packet = replay_packets([repetition], "clip", real_config)[0].to_dict()
    schema = json.loads((Path(__file__).parents[1] / "schemas" / "analysis-result.schema.json").read_text())
    validate(packet, schema)
    assert packet["session_id"].startswith("real-pose-simulated-force-")

