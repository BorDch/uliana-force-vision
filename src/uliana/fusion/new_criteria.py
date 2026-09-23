from __future__ import annotations

from uliana.contracts.models import AssessmentResult
from uliana.video.features import RepetitionCameraFeatures
from .reliability import condition_gate


def _persistent_fraction(values: list[tuple[int, bool]], minimum_ms: int) -> tuple[float, int]:
    if not values:
        return 0, 0
    active_time = 0
    longest = 0
    start = None
    for (timestamp, active), (next_timestamp, _) in zip(values, values[1:]):
        if active:
            active_time += max(0, next_timestamp - timestamp)
            start = timestamp if start is None else start
            longest = max(longest, next_timestamp - start)
        else:
            start = None
    duration = max(1, values[-1][0] - values[0][0])
    return active_time / duration, longest


def assess_head_neck_alignment(features: RepetitionCameraFeatures, phase_confidence: float, config: dict) -> AssessmentResult:
    """Assess head/neck alignment relative to spine.
    
    The head should be an extension of the spine - neither lower nor higher.
    For side view: uses ear position relative to shoulder-hip line.
    For front view: uses nose position relative to shoulder midpoint.
    
    Reference: suprak-2013 - head position as part of spinal alignment.
    """
    condition = "head_neck_alignment"
    data = features.head_neck_data
    
    if not data:
        return AssessmentResult(condition, "unavailable", None, "required_landmarks_unavailable",
                                features.rep_id, "camera",
                                {"reason": "Head/neck landmarks not available in this view"})
    
    viewpoint = features.viewpoint
    valid = features.valid_frame_fraction
    available = True
    
    allowed, reason, confidence = condition_gate(
        viewpoint, features.viewpoint_confidence, valid, available,
        phase_confidence >= config["phase_segmentation"]["minimum_signal_confidence"],
        condition, config)
    
    if not allowed:
        return AssessmentResult(condition, "unavailable", None, reason, features.rep_id, "camera",
                                {"valid_frame_fraction": valid})
    
    deviations = [abs(item[1]) for item in data]
    if not deviations:
        return AssessmentResult(condition, "unavailable", None, "insufficient_head_data",
                                features.rep_id, "camera", None)
    
    limits = config["camera_conditions"]["head_neck"]
    max_deviation = max(deviations)
    mean_deviation = sum(item[1] for item in data) / len(data)
    
    flags = [(t, abs(dev) > limits["maximum_normalized_deviation"]) for t, dev, _ in data]
    fraction, longest = _persistent_fraction(flags, limits["minimum_persistence_ms"])
    detected = fraction >= limits["minimum_persistence_fraction"] and longest >= limits["minimum_persistence_ms"]
    
    head_position_issue = None
    if mean_deviation > 0.05:
        head_position_issue = "head_too_high"
    elif mean_deviation < -0.05:
        head_position_issue = "head_too_low"
    
    evidence = {
        "maximum_normalized_head_deviation": max_deviation,
        "mean_head_deviation": mean_deviation,
        "persistent_fraction": fraction,
        "longest_persistent_duration_ms": longest,
        "experimental_threshold": limits["maximum_normalized_deviation"],
    }
    if head_position_issue:
        evidence["head_position"] = head_position_issue
    
    return AssessmentResult(condition,
                            "condition_detected" if detected else "adequate",
                            confidence,
                            "persistent_head_deviation" if detected else "head_position_within_range",
                            features.rep_id, "camera", evidence)


def assess_elbow_to_torso_flare(features: RepetitionCameraFeatures, phase_confidence: float, config: dict) -> AssessmentResult:
    """Assess elbow flare angle relative to torso.
    
    Measures how far elbows are flared out from the body.
    Side view cannot assess flare (arm is edge-on).
    Front/oblique views can estimate using shoulder-elbow geometry.
    
    Reference: suprak-2013 - shoulder impingement risk with elbow flare.
    """
    condition = "elbow_to_torso_flare"
    viewpoint = features.viewpoint
    
    if viewpoint == "side":
        return AssessmentResult(condition, "unavailable", None, "viewpoint_not_supported",
                                features.rep_id, "camera",
                                {"reason": "Elbow flare requires frontal-plane view (front or oblique); side view shows arm edge-on"})
    
    if not features.elbow_angles:
        return AssessmentResult(condition, "unavailable", None, "required_landmarks_unavailable",
                                features.rep_id, "camera",
                                {"reason": "Elbow landmark data not available"})
    
    allowed, reason, confidence = condition_gate(
        viewpoint, features.viewpoint_confidence, features.valid_frame_fraction, True,
        phase_confidence >= config["phase_segmentation"]["minimum_signal_confidence"],
        condition, config)
    
    if not allowed:
        return AssessmentResult(condition, "unavailable", None, reason, features.rep_id, "camera",
                                {"valid_frame_fraction": features.valid_frame_fraction})
    
    limits = config["camera_conditions"]["elbow_flare"]
    
    bottom_elbows = []
    if features.bottom_ms is not None:
        bottom_elbows = [v for t, v in features.elbow_angles
                         if abs(t - features.bottom_ms) <= config["camera_conditions"]["depth_proxy"]["bottom_window_ms"]]
    
    if not bottom_elbows:
        bottom_elbows = [v for _, v in features.elbow_angles]
    
    if not bottom_elbows:
        return AssessmentResult(condition, "unavailable", None, "insufficient_elbow_data",
                                features.rep_id, "camera", None)
    
    # Estimate flare from elbow angles (simplified heuristic)
    # Higher elbow angle (more extended) can indicate less effective positioning
    # For proper flare angle, we'd need shoulder-elbow-torso geometry
    mean_elbow = sum(bottom_elbows) / len(bottom_elbows)
    
    # This is an approximation - full implementation needs 3D analysis
    # For now, we note that true flare measurement requires frontal plane analysis
    return AssessmentResult(condition, "unavailable", confidence,
                            "flare_measurement_requires_3d_analysis",
                            features.rep_id, "camera",
                            {
                                "reason": "True elbow flare angle requires shoulder-elbow-torso computation in frontal plane",
                                "supported_viewpoints": ["front", "oblique"],
                                "mean_elbow_angle_deg": mean_elbow,
                                "note": "Full implementation needs per-frame landmark analysis"
                            })


def assess_hand_placement(features: RepetitionCameraFeatures, phase_confidence: float, config: dict) -> AssessmentResult:
    """Assess hand placement relative to shoulders.
    
    Hands should be positioned approximately under the shoulders.
    Changing hand position changes muscle activation patterns.
    
    Reference: donkers-1993, kellis-1993 - hand position effects.
    """
    condition = "hand_placement"
    viewpoint = features.viewpoint
    data = features.hand_placement_data
    
    if viewpoint == "side":
        return AssessmentResult(condition, "unavailable", None, "viewpoint_not_supported",
                                features.rep_id, "camera",
                                {"reason": "Hand placement requires frontal-plane view to compare wrist and shoulder positions"})
    
    if not data:
        return AssessmentResult(condition, "unavailable", None, "required_landmarks_unavailable",
                                features.rep_id, "camera",
                                {"reason": "Hand/shoulder landmark data not available in this view"})
    
    allowed, reason, confidence = condition_gate(
        viewpoint, features.viewpoint_confidence, features.valid_frame_fraction, True,
        phase_confidence >= config["phase_segmentation"]["minimum_signal_confidence"],
        condition, config)
    
    if not allowed:
        return AssessmentResult(condition, "unavailable", None, reason, features.rep_id, "camera",
                                {"valid_frame_fraction": features.valid_frame_fraction})
    
    all_offsets = []
    for _, left_offset, right_offset, _ in data:
        all_offsets.append(abs(left_offset))
        all_offsets.append(abs(right_offset))
    
    if not all_offsets:
        return AssessmentResult(condition, "unavailable", None, "insufficient_hand_data",
                                features.rep_id, "camera", None)
    
    mean_offset = sum(all_offsets) / len(all_offsets)
    max_offset = max(all_offsets)
    
    limits = config["camera_conditions"]["hand_placement"]
    
    flags = [(t, max(abs(left), abs(right)) > limits["maximum_wrist_offset"])
             for t, left, right, _ in data]
    fraction, longest = _persistent_fraction(flags, limits["minimum_persistence_ms"])
    detected = fraction >= limits["minimum_persistence_fraction"] and longest >= limits["minimum_persistence_ms"]
    
    evidence = {
        "mean_wrist_offset": mean_offset,
        "maximum_wrist_offset": max_offset,
        "persistent_fraction": fraction,
        "longest_persistent_duration_ms": longest,
        "experimental_threshold": limits["maximum_wrist_offset"],
    }
    
    return AssessmentResult(condition,
                            "condition_detected" if detected else "adequate",
                            confidence,
                            "hand_position_deviation" if detected else "hand_position_within_range",
                            features.rep_id, "camera", evidence)
