from __future__ import annotations

import json
from pathlib import Path

from uliana.contracts.models import AssessmentResult
from uliana.video.features import RepetitionCameraFeatures
from .reliability import condition_gate


def _persistent_fraction(values: list[tuple[int, bool]], maximum_gap_ms: int) -> tuple[float, int]:
    if not values:
        return 0, 0
    
    active_time = 0
    longest = 0
    start = None
    
    for (timestamp, active), (next_timestamp, _) in zip(values, values[1:]):
        if active and 0 < next_timestamp - timestamp <= maximum_gap_ms:
            active_time += max(0, next_timestamp - timestamp)
            start = timestamp if start is None else start
            longest = max(longest, next_timestamp - start)
        else:
            start = None
    
    duration = max(1, values[-1][0] - values[0][0])
    return active_time / duration, longest


def assess_head_neck_alignment(
    features: RepetitionCameraFeatures,
    phase_confidence: float,
    config: dict
) -> AssessmentResult:
    """Assess head/neck alignment relative to spine.
    
    The head should be an extension of the spine - neither lower nor higher.
    Uses ear/nose position relative to shoulder-hip line.
    
    Reference: https://doi.org/10.1519/SSC.0b013e31826d877b
    """
    condition = "head_neck_alignment"
    data = features.head_neck_data
    
    if not data:
        return AssessmentResult(
            condition=condition,
            result="unavailable",
            confidence=None,
            reason="required_landmarks_unavailable",
            rep_id=features.rep_id,
            modality="camera",
            evidence={"reason": "Head/neck landmarks not available"}
        )
    
    viewpoint = features.viewpoint
    valid = min(features.valid_frame_fraction, len(data) / features.frame_count) if features.frame_count else 0
    available = True
    
    allowed, reason, confidence = condition_gate(
        viewpoint=viewpoint,
        viewpoint_confidence=features.viewpoint_confidence,
        valid_fraction=valid,
        landmarks_available=available,
        phase_reliable=phase_confidence >= config["phase_segmentation"]["minimum_signal_confidence"],
        condition=condition,
        config=config
    )
    
    if not allowed:
        return AssessmentResult(
            condition=condition,
            result="unavailable",
            confidence=confidence,
            reason=reason,
            rep_id=features.rep_id,
            modality="camera",
            evidence={"valid_frame_fraction": valid}
        )
    
    limits = config["camera_conditions"].get("head_neck", _RESEARCH_LIMITS["head_neck"])
    max_deviation = limits.get("maximum_normalized_deviation", 0.15)
    min_persistence_fraction = limits.get("minimum_persistence_fraction", 0.25)
    min_persistence_ms = limits.get("minimum_persistence_ms", 250)
    
    # data format: (timestamp, normalized_deviation, ear_y_position)
    deviations = [(t, abs(dev)) for t, dev, _ in data]
    
    if not deviations:
        return AssessmentResult(
            condition=condition,
            result="unavailable",
            confidence=None,
            reason="insufficient_head_data",
            rep_id=features.rep_id,
            modality="camera",
            evidence={"reason": "No head position data extracted"}
        )
    
    flags = [(t, d > max_deviation) for t, d in deviations]
    fraction, longest = _persistent_fraction(flags, config["maximum_pose_gap_ms"])
    
    max_deviation_value = max(d for _, d in deviations)
    
    detected = fraction >= min_persistence_fraction and longest >= min_persistence_ms
    
    evidence = {
        "maximum_normalized_deviation": max_deviation_value,
        "persistent_fraction": fraction,
        "longest_persistent_duration_ms": longest,
        "experimental_threshold": max_deviation,
    }
    
    return AssessmentResult(
        condition=condition,
        result="condition_detected" if detected else "adequate",
        confidence=confidence,
        reason="persistent_head_deviation" if detected else "head_alignment_within_range",
        rep_id=features.rep_id,
        modality="camera",
        evidence=evidence
    )


def assess_elbow_to_torso_flare(
    features: RepetitionCameraFeatures,
    phase_confidence: float,
    config: dict
) -> AssessmentResult:
    """Assess elbow flare angle relative to torso.
    
    Beginners often put elbows at 90 degrees to torso, increasing shoulder stress.
    Elbows should be kept around 45 degrees to the body.
    
    Reference: https://doi.org/10.4085/1062-6050-48.5.08
    """
    condition = "elbow_to_torso_flare"
    data = features.elbow_flare_data
    
    if not data:
        viewpoint = features.viewpoint
        if viewpoint == "side":
            return AssessmentResult(
                condition=condition,
                result="unavailable",
                confidence=None,
                reason="viewpoint_not_supported",
                rep_id=features.rep_id,
                modality="camera",
                evidence={
                    "reason": "Elbow flare requires front or oblique view; side view shows arm edge-on",
                    "supported_viewpoints": ["front", "oblique"]
                }
            )
        return AssessmentResult(
            condition=condition,
            result="unavailable",
            confidence=None,
            reason="required_landmarks_unavailable",
            rep_id=features.rep_id,
            modality="camera",
            evidence={"reason": "Elbow flare landmarks not available"}
        )
    
    viewpoint = features.viewpoint
    valid = min(features.valid_frame_fraction, len(data) / features.frame_count) if features.frame_count else 0
    available = True
    
    allowed, reason, confidence = condition_gate(
        viewpoint=viewpoint,
        viewpoint_confidence=features.viewpoint_confidence,
        valid_fraction=valid,
        landmarks_available=available,
        phase_reliable=phase_confidence >= config["phase_segmentation"]["minimum_signal_confidence"],
        condition=condition,
        config=config
    )
    
    if not allowed:
        return AssessmentResult(
            condition=condition,
            result="unavailable",
            confidence=confidence,
            reason=reason,
            rep_id=features.rep_id,
            modality="camera",
            evidence={"valid_frame_fraction": valid}
        )
    
    limits = config["camera_conditions"].get("elbow_flare", _RESEARCH_LIMITS["elbow_flare"])
    max_flare_angle = limits.get("maximum_flare_angle_deg", 60.0)
    min_persistence_fraction = limits.get("minimum_persistence_fraction", 0.25)
    min_persistence_ms = limits.get("minimum_persistence_ms", 250)
    
    # data format: (timestamp, left_flare_angle, right_flare_angle)
    max_angles = [(t, max(l, r)) for t, l, r in data]
    
    if not max_angles:
        return AssessmentResult(
            condition=condition,
            result="unavailable",
            confidence=None,
            reason="insufficient_flare_data",
            rep_id=features.rep_id,
            modality="camera",
            evidence={"reason": "No elbow flare data extracted"}
        )
    
    flags = [(t, angle > max_flare_angle) for t, angle in max_angles]
    fraction, longest = _persistent_fraction(flags, config["maximum_pose_gap_ms"])
    
    max_flare_value = max(angle for _, angle in max_angles)
    mean_left = sum(l for _, l, _ in data) / len(data)
    mean_right = sum(r for _, _, r in data) / len(data)
    
    detected = fraction >= min_persistence_fraction and longest >= min_persistence_ms
    
    evidence = {
        "maximum_flare_angle_deg": max_flare_value,
        "mean_left_flare_deg": mean_left,
        "mean_right_flare_deg": mean_right,
        "persistent_fraction": fraction,
        "longest_persistent_duration_ms": longest,
        "experimental_threshold_deg": max_flare_angle,
        "interpretation": "Experimental projected upper-arm/torso angle; not a joint-loading or injury-risk estimate"
    }
    
    return AssessmentResult(
        condition=condition,
        result="condition_detected" if detected else "adequate",
        confidence=confidence,
        reason="persistent_elbow_flare" if detected else "elbow_position_within_range",
        rep_id=features.rep_id,
        modality="camera",
        evidence=evidence
    )


def assess_hand_placement(
    features: RepetitionCameraFeatures,
    phase_confidence: float,
    config: dict
) -> AssessmentResult:
    """Assess hand placement relative to shoulders.
    
    Hands should be positioned approximately under the shoulders.
    
    Reference: https://pubmed.ncbi.nlm.nih.gov/2334780/
    Reference: https://doi.org/10.1016/0021-9290(93)90026-b
    """
    condition = "hand_placement"
    data = features.hand_placement_data
    
    if not data:
        viewpoint = features.viewpoint
        if viewpoint == "side":
            return AssessmentResult(
                condition=condition,
                result="unavailable",
                confidence=None,
                reason="viewpoint_not_supported",
                rep_id=features.rep_id,
                modality="camera",
                evidence={
                    "reason": "Hand placement requires front or oblique view; side view does not show hand width",
                    "supported_viewpoints": ["front", "oblique"]
                }
            )
        return AssessmentResult(
            condition=condition,
            result="unavailable",
            confidence=None,
            reason="required_landmarks_unavailable",
            rep_id=features.rep_id,
            modality="camera",
            evidence={"reason": "Hand placement landmarks not available"}
        )
    
    viewpoint = features.viewpoint
    valid = min(features.valid_frame_fraction, len(data) / features.frame_count) if features.frame_count else 0
    available = True
    
    allowed, reason, confidence = condition_gate(
        viewpoint=viewpoint,
        viewpoint_confidence=features.viewpoint_confidence,
        valid_fraction=valid,
        landmarks_available=available,
        phase_reliable=phase_confidence >= config["phase_segmentation"]["minimum_signal_confidence"],
        condition=condition,
        config=config
    )
    
    if not allowed:
        return AssessmentResult(
            condition=condition,
            result="unavailable",
            confidence=confidence,
            reason=reason,
            rep_id=features.rep_id,
            modality="camera",
            evidence={"valid_frame_fraction": valid}
        )
    
    limits = config["camera_conditions"].get("hand_placement", _RESEARCH_LIMITS["hand_placement"])
    max_wrist_offset = limits.get("maximum_wrist_offset", 0.4)
    min_persistence_fraction = limits.get("minimum_persistence_fraction", 0.25)
    min_persistence_ms = limits.get("minimum_persistence_ms", 250)
    
    # data format: (timestamp, left_wrist_offset, right_wrist_offset, shoulder_mid_x)
    # offset: 0 = under shoulder, positive = outside, negative = inside
    max_offsets = [(t, max(abs(l), abs(r))) for t, l, r, _ in data]
    
    if not max_offsets:
        return AssessmentResult(
            condition=condition,
            result="unavailable",
            confidence=None,
            reason="insufficient_hand_data",
            rep_id=features.rep_id,
            modality="camera",
            evidence={"reason": "No hand placement data extracted"}
        )
    
    flags = [(t, offset > max_wrist_offset) for t, offset in max_offsets]
    fraction, longest = _persistent_fraction(flags, config["maximum_pose_gap_ms"])
    
    max_offset_value = max(offset for _, offset in max_offsets)
    mean_left = sum(l for _, l, _, _ in data) / len(data)
    mean_right = sum(r for _, _, r, _ in data) / len(data)
    
    detected = fraction >= min_persistence_fraction and longest >= min_persistence_ms
    
    evidence = {
        "maximum_wrist_offset": max_offset_value,
        "mean_left_wrist_offset": mean_left,
        "mean_right_wrist_offset": mean_right,
        "persistent_fraction": fraction,
        "longest_persistent_duration_ms": longest,
        "experimental_threshold": max_wrist_offset,
        "units": "shoulder_widths",
        "interpretation": "0 = hands under shoulders; positive = outside (wider); negative = inside (narrower)"
    }
    
    return AssessmentResult(
        condition=condition,
        result="condition_detected" if detected else "adequate",
        confidence=confidence,
        reason="persistent_hand_misplacement" if detected else "hand_position_within_range",
        rep_id=features.rep_id,
        modality="camera",
        evidence=evidence
    )
_RESEARCH_LIMITS = json.loads((Path(__file__).resolve().parents[3] / "configs" / "research_preview.v1.json").read_text(encoding="utf-8"))["camera_conditions"]
