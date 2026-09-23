from __future__ import annotations


def condition_gate(viewpoint:str,viewpoint_confidence:float|None,valid_fraction:float,landmarks_available:bool,
                   phase_reliable:bool,condition:str,config:dict)->tuple[bool,str|None,float]:
    limits=config["camera_conditions"]
    if viewpoint=="unknown":return False,"viewpoint_not_supported",0
    if condition in ("body_alignment_deviation","push_up_depth_proxy") and viewpoint=="front":return False,"viewpoint_not_supported",0
    if condition in ("elbow_to_torso_flare", "hand_placement") and viewpoint == "side":return False,"viewpoint_not_supported",0
    if condition == "head_neck_alignment" and viewpoint == "front":return False,"viewpoint_not_supported",0
    required_confidence=limits["oblique_minimum_viewpoint_confidence"] if viewpoint=="oblique" else limits["minimum_viewpoint_confidence"]
    if viewpoint_confidence is None or viewpoint_confidence<required_confidence:return False,"viewpoint_confidence_insufficient",0
    if not phase_reliable:return False,"phase_detection_unreliable",0
    if not landmarks_available:return False,"required_landmarks_unavailable",0
    if valid_fraction<limits["minimum_valid_frame_fraction"]:return False,"insufficient_valid_frames",0
    confidence=min(.92,.35*valid_fraction+.35*viewpoint_confidence+.3*(.85 if viewpoint=="oblique" else .95))
    return True,None,confidence


def pressure_condition_gate(*, synchronization_status:str, calibration_valid:bool, expected_channels_available:bool,
                            coverage:float, saturation_fraction:float, critical_quality_codes:list[str],
                            repetition_duration_ms:int, persistence_ms:int|None, config:dict)->tuple[bool,str|None,float]:
    if synchronization_status!="acceptable":return False,"synchronization_unavailable_or_poor",0
    if not calibration_valid:return False,"pressure_calibration_unavailable",0
    if not expected_channels_available:return False,"required_pressure_channels_missing",0
    if coverage<config["minimum_pressure_coverage"]:return False,"insufficient_pressure_coverage",0
    if saturation_fraction>config["maximum_saturation_fraction"]:return False,"pressure_saturation",0
    if critical_quality_codes:return False,"critical_pressure_quality_issue",0
    if repetition_duration_ms<config["minimum_repetition_duration_ms"]:return False,"repetition_too_short_for_pressure_assessment",0
    if persistence_ms is not None and persistence_ms<config["balance"]["minimum_persistence_ms"]:return False,"insufficient_pressure_persistence",0
    return True,None,min(.92,.45*coverage+.25+.2*(1-saturation_fraction))
