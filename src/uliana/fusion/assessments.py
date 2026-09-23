from __future__ import annotations

from uliana.contracts.models import AssessmentResult
from uliana.video.features import RepetitionCameraFeatures
from .reliability import condition_gate
from .aggregation import RepetitionPressureAggregation
from .reliability import pressure_condition_gate


def _persistent_fraction(values:list[tuple[int,bool]],minimum_ms:int)->tuple[float,int]:
    if not values:return 0,0
    active_time=0;longest=0;start=None
    for (timestamp,active),(next_timestamp,_) in zip(values,values[1:]):
        if active:active_time+=max(0,next_timestamp-timestamp);start=timestamp if start is None else start;longest=max(longest,next_timestamp-start)
        else:start=None
    duration=max(1,values[-1][0]-values[0][0]);return active_time/duration,longest


def assess_body_alignment(features:RepetitionCameraFeatures,phase_confidence:float,config:dict)->AssessmentResult:
    condition="body_alignment_deviation"; values=features.normalized_hip_displacement; angles=features.alignment_angle_deviation_deg
    available=bool(values and angles); valid=len(values)/features.frame_count if features.frame_count else 0
    allowed,reason,confidence=condition_gate(features.viewpoint,features.viewpoint_confidence,valid,available,phase_confidence>=config["phase_segmentation"]["minimum_signal_confidence"],condition,config)
    if not allowed:return AssessmentResult(condition,"unavailable",None,reason,features.rep_id,"camera",{"valid_frame_fraction":valid})
    limits=config["camera_conditions"]["body_alignment"]
    by_time={t:value for t,value in values}; angle_by_time={t:value for t,value in angles}
    flags=[(t,abs(value)>limits["normalized_hip_displacement"] or angle_by_time.get(t,0)>limits["angle_deviation_deg"]) for t,value in values]
    fraction,longest=_persistent_fraction(flags,limits["minimum_persistence_ms"])
    detected=fraction>=limits["minimum_persistence_fraction"] and longest>=limits["minimum_persistence_ms"]
    evidence={"maximum_alignment_angle_deviation_deg":max(value for _,value in angles),
        "maximum_normalized_hip_displacement":max(abs(value) for _,value in values),
        "mean_signed_hip_displacement":sum(value for _,value in features.signed_hip_displacement)/len(features.signed_hip_displacement),
        "persistent_fraction":fraction,"longest_persistent_duration_ms":longest,
        "experimental_thresholds":limits}
    return AssessmentResult(condition,"condition_detected" if detected else "adequate",confidence,
        "persistent_body_alignment_deviation" if detected else "body_alignment_within_configured_range",features.rep_id,"camera",evidence)


def assess_depth_proxy(features:RepetitionCameraFeatures,phase_confidence:float,config:dict)->AssessmentResult:
    condition="push_up_depth_proxy"; minimum=features.minimum_elbow_angle_deg
    available=minimum is not None; valid=features.valid_frame_fraction
    allowed,reason,confidence=condition_gate(features.viewpoint,features.viewpoint_confidence,valid,available,phase_confidence>=config["phase_segmentation"]["minimum_signal_confidence"],condition,config)
    if not allowed:return AssessmentResult(condition,"unavailable",None,reason,features.rep_id,"camera",{"valid_frame_fraction":valid})
    if features.bottom_ms is None:return AssessmentResult(condition,"unavailable",None,"phase_detection_unreliable",features.rep_id,"camera",None)
    depth_config=config["camera_conditions"]["depth_proxy"]
    bottom_values=[value for timestamp,value in features.elbow_angles if abs(timestamp-features.bottom_ms)<=depth_config["bottom_window_ms"]]
    if len(bottom_values)<depth_config["minimum_bottom_samples"]:
        return AssessmentResult(condition,"unavailable",None,"phase_detection_unreliable",features.rep_id,"camera",{"bottom_sample_count":len(bottom_values)})
    minimum=min(bottom_values);limit=depth_config["minimum_elbow_angle_deg"]
    detected=minimum>limit
    return AssessmentResult(condition,"condition_detected" if detected else "adequate",confidence,
        "insufficient_range_of_motion" if detected else "minimum_elbow_angle_within_configured_range",features.rep_id,"camera",
        {"minimum_elbow_angle_deg":minimum,"experimental_threshold_deg":limit,"interpretation":"camera_observable_proxy_not_chest_floor_contact"})


def _pressure_evidence(aggregation:RepetitionPressureAggregation,measurement:str,value,unit:str|None,
                       confidence:float|None,flags:list[str],supported:bool,reason:str|None)->dict:
    return {"source_modality":"pressure","measurement":measurement,"value":value,"unit":unit,
        "valid_interval":{"start_ms":aggregation.start_ms,"end_ms":aggregation.end_ms},
        "coverage":aggregation.sampling_coverage,"confidence":confidence,"quality_flags":flags,
        "assessment_supported":supported,"reason":reason}


def assess_pressure_balance(aggregation:RepetitionPressureAggregation,synchronization_status:str,
                            expected_channel_count:int,critical_codes:list[str],config:dict)->AssessmentResult:
    condition="left_right_pressure_balance";duration=aggregation.end_ms-aggregation.start_ms
    persistence=aggregation.imbalance_persistence_ms
    allowed,reason,confidence=pressure_condition_gate(synchronization_status=synchronization_status,
        calibration_valid=aggregation.calibration_state=="calibrated",
        expected_channels_available=expected_channel_count>0 and aggregation.channel_count>=expected_channel_count,
        coverage=aggregation.sampling_coverage,saturation_fraction=aggregation.saturation_fraction,
        critical_quality_codes=critical_codes,repetition_duration_ms=duration,
        persistence_ms=None,config=config)
    regions_available=bool(aggregation.region_time_series)
    if allowed and not regions_available:allowed=False;reason="required_pressure_region_missing";confidence=0
    evidence=_pressure_evidence(aggregation,"symmetric palm-region imbalance",
        aggregation.mean_region_imbalance_percent,"percent",confidence or None,
        sorted(set(aggregation.quality_flags+critical_codes)),allowed,reason)
    evidence.update({"maximum_imbalance_percent":aggregation.maximum_region_imbalance_percent,
        "persistence_fraction":aggregation.imbalance_persistence_fraction,
        "persistence_ms":aggregation.imbalance_persistence_ms,
        "interpretation":"descriptive load distribution; asymmetry is not universally incorrect technique"})
    if not allowed:return AssessmentResult(condition,"unavailable",None,reason,aggregation.rep_id,"pressure",evidence)
    limits=config["balance"]
    detected=(aggregation.maximum_region_imbalance_percent or 0)>=limits["imbalance_percent"] and \
        (aggregation.imbalance_persistence_fraction or 0)>=limits["minimum_persistence_fraction"] and \
        (persistence or 0)>=limits["minimum_persistence_ms"]
    return AssessmentResult(condition,"condition_detected" if detected else "adequate",confidence,
        "persistent_palm_load_imbalance" if detected else "palm_load_distribution_within_configured_range",
        aggregation.rep_id,"pressure",evidence)


def assess_hand_pressure_stability(aggregation:RepetitionPressureAggregation,synchronization_status:str,
                                   expected_channel_count:int,critical_codes:list[str],config:dict)->AssessmentResult:
    condition="hand_pressure_stability";settings=config["hand_pressure_stability"]
    threshold=settings.get("maximum_cop_displacement_cells")
    reason=None
    if not aggregation.centre_of_pressure_trajectory:reason="calibrated_grid_unavailable"
    elif threshold is None:reason="trainer_threshold_not_configured"
    allowed,gate_reason,confidence=pressure_condition_gate(synchronization_status=synchronization_status,
        calibration_valid=aggregation.calibration_state=="calibrated",
        expected_channels_available=expected_channel_count>0 and aggregation.channel_count>=expected_channel_count,
        coverage=aggregation.sampling_coverage,saturation_fraction=aggregation.saturation_fraction,
        critical_quality_codes=critical_codes,repetition_duration_ms=aggregation.end_ms-aggregation.start_ms,
        persistence_ms=None,config=config)
    reason=gate_reason if not allowed else reason
    evidence=_pressure_evidence(aggregation,"centre-of-pressure path length",
        aggregation.centre_of_pressure_displacement_cells,"grid_cells",confidence or None,
        sorted(set(aggregation.quality_flags+critical_codes)),allowed and reason is None,reason)
    if reason:return AssessmentResult(condition,"unavailable",None,reason,aggregation.rep_id,"pressure",evidence)
    detected=(aggregation.centre_of_pressure_displacement_cells or 0)>threshold
    return AssessmentResult(condition,"condition_detected" if detected else "adequate",confidence,
        "cop_movement_exceeds_trainer_configured_threshold" if detected else "cop_movement_within_trainer_configured_threshold",
        aggregation.rep_id,"pressure",evidence)


def assess_pressure_signal_quality(aggregation:RepetitionPressureAggregation,critical_codes:list[str])->AssessmentResult:
    bad=bool(critical_codes or aggregation.sampling_coverage<1)
    evidence=_pressure_evidence(aggregation,"pressure stream quality",aggregation.sampling_coverage,"fraction",
        1.0,sorted(set(aggregation.quality_flags+critical_codes)),True,None)
    return AssessmentResult("pressure_signal_quality","condition_detected" if bad else "adequate",1.0,
        "pressure_quality_issue_present" if bad else "pressure_signal_quality_adequate",aggregation.rep_id,"pressure",evidence)
