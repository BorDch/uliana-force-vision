from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .pose_adapter import PoseFrame
from .scoring import component_scores, decide
from .state_machine import PushUpStateMachine, State
from .types import AnalysisResult, ReliabilityState, RepetitionSummary
from .video_geometry import SIDES, Landmark, choose_visible_side, geometry_for_side


@dataclass(frozen=True)
class VideoRepetition:
    rep_id: int
    start_ms: int
    bottom_ms: int | None
    end_ms: int
    minimum_elbow_angle_deg: float
    maximum_body_line_error_deg: float
    reliable_frame_fraction: float
    cue: str
    abstained: bool
    reason: str | None


def pose_frame_from_dict(value: dict[str, Any]) -> PoseFrame:
    landmarks = {name: Landmark(**point) for name, point in value.get("landmarks", {}).items()}
    return PoseFrame(value["frame_index"], value["timestamp_ms"], value["timestamp_source"], value["detected"],
                     landmarks, value.get("inference_ms", 0.0), value.get("error"),
                     {name: Landmark(**point) for name, point in (value.get("world_landmarks") or {}).items()} or None)


def analyze_pose_frames(frames: list[PoseFrame], width: int, height: int, config: dict) -> tuple[list[dict], list[VideoRepetition], str | None, str]:
    calibration = [frame.landmarks for frame in frames if frame.detected][:config["side_selection"]["calibration_frames"]]
    side, side_reason = choose_visible_side(calibration, config["side_selection"]["minimum_margin"])
    machine = PushUpStateMachine(**config["state_machine"])
    diagnostics: list[dict] = []
    repetitions: list[VideoRepetition] = []
    active: list[dict] = []
    start_ms = bottom_ms = last_reliable_ms = None
    active_total = 0
    for frame in frames:
        angle = body_error = None
        quality = 0.0
        reason = frame.error or (None if frame.detected else "pose_not_detected")
        if reason is None and side is not None:
            angle, body_error, quality, reason = geometry_for_side(
                frame.landmarks, side, width, height, config["min_required_landmark_quality"])
        elif side is None and reason is None:
            reason = "visible_side_unavailable"
        reliable = reason is None
        failing_landmarks = []
        if frame.detected and side is not None:
            failing_landmarks = [name for name in SIDES[side]
                                 if name not in frame.landmarks
                                 or frame.landmarks[name].quality < config["min_required_landmark_quality"]]
        gap_reset = False
        if reliable and last_reliable_ms is not None and frame.timestamp_ms - last_reliable_ms > config["max_pose_gap_ms"]:
            machine.reset(); active = []; active_total = 0; start_ms = bottom_ms = None; gap_reset = True
        if not reliable and last_reliable_ms is not None and frame.timestamp_ms - last_reliable_ms > config["max_pose_gap_ms"]:
            machine.reset(); active = []; active_total = 0; start_ms = bottom_ms = None; gap_reset = True
        if start_ms is not None:
            active_total += 1
        completed = False
        phase = "unavailable"
        if reliable:
            old_state = machine.state
            completed = machine.update(angle)
            if old_state == State.READY and machine.state == State.DESCENDING:
                start_ms, bottom_ms, active, active_total = frame.timestamp_ms, None, [], 1
            if machine.state == State.DOWN and bottom_ms is None:
                bottom_ms = frame.timestamp_ms
            if machine.state == State.READY: phase = "up"
            elif machine.state == State.DOWN: phase = "down"
            else: phase = "transition"
            active.append({"timestamp_ms": frame.timestamp_ms, "elbow_angle_deg": angle,
                           "body_line_error_deg": body_error, "quality": quality})
            last_reliable_ms = frame.timestamp_ms
        diagnostic = {"frame_index": frame.frame_index, "timestamp_ms": frame.timestamp_ms,
            "timestamp_source": frame.timestamp_source, "pose_detected": frame.detected, "selected_side": side,
            "image_plane_elbow_angle_deg": angle, "image_plane_body_line_deviation_deg": body_error,
            "required_landmark_quality": quality, "assessment_available": reliable, "reliability_reason": reason,
            "failing_required_landmarks": failing_landmarks,
            "gap_reset": gap_reset, "phase": phase, "rep_count": machine.rep_count}
        diagnostics.append(diagnostic)
        if completed and active and start_ms is not None:
            min_angle = min(x["elbow_angle_deg"] for x in active)
            max_body = max(x["body_line_error_deg"] for x in active)
            mean_quality = sum(x["quality"] for x in active) / len(active)
            summary = RepetitionSummary(machine.rep_count, None, None, None, None, None, None, min_angle, max_body, mean_quality)
            coverage = len(active) / max(1, active_total)
            pose_reliable = mean_quality >= config["min_required_landmark_quality"] and coverage >= config["min_rep_pose_coverage"]
            reliability = ReliabilityState(pose_reliable, None if pose_reliable else "insufficient_pose_coverage", pose_reliable, False)
            decision_config = {"thresholds": config["thresholds"]}
            decision = decide(summary, reliability, decision_config, "camera")
            repetitions.append(VideoRepetition(machine.rep_count, start_ms, bottom_ms, frame.timestamp_ms, min_angle,
                                                max_body, coverage, decision.cue, decision.abstained, decision.reason))
            active = []; active_total = 0; start_ms = bottom_ms = None
    return diagnostics, repetitions, side, side_reason


def replay_packets(repetitions: list[VideoRepetition], session_id: str, config: dict) -> list[AnalysisResult]:
    """Compatibility adapter only for explicitly simulated-force demonstrations."""
    force = config["simulated_force"]
    output = []
    for repetition in repetitions:
        summary = RepetitionSummary(repetition.rep_id, force["left_force_n"], force["right_force_n"], 0, 0, 0, 0,
                                    repetition.minimum_elbow_angle_deg, repetition.maximum_body_line_error_deg, repetition.reliable_frame_fraction)
        phase1_config = {"thresholds": config["thresholds"],
                         "scoring": {"balance_weight": .4, "depth_weight": .3, "alignment_weight": .3}}
        quality = component_scores(summary, phase1_config)
        decision = decide(summary, ReliabilityState(True, None, True, True), phase1_config, "camera")
        output.append(AnalysisResult("1.0", "toy_simulator", f"real-pose-simulated-force-{session_id}", repetition.end_ms,
            repetition.rep_id, "up", {"left_force_n": force["left_force_n"], "right_force_n": force["right_force_n"],
            "asymmetry_percent": 0.0, "elbow_angle_deg": round(repetition.minimum_elbow_angle_deg, 2),
            "body_line_error_deg": round(repetition.maximum_body_line_error_deg, 2)}, quality, asdict(decision)))
    return output


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")
