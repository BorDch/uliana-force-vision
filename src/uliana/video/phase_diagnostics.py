from __future__ import annotations

import json
import math
import statistics
from collections import Counter

from uliana.contracts.models import VideoObservation
from .phases import candidate_signals, phase_thresholds, select_phase_signal


def rank_phase_signals(observations:list[VideoObservation],viewpoint:str,observable_side:str,config:dict)->list[dict]:
    limits=config["phase_segmentation"];names=limits["candidates"][viewpoint]
    frame_values=[candidate_signals(item,observable_side,config) if item.pose.detected else {} for item in observations]
    ranked=[]
    for priority,name in enumerate(names):
        values=[(item.timestamp_ms,signals.get(name)) for item,signals in zip(observations,frame_values) if signals.get(name) is not None]
        coverage=len(values)/len(observations) if observations else 0
        raw=[value for _,value in values];span=max(raw)-min(raw) if raw else 0
        differences=[b-a for a,b in zip(raw,raw[1:])]
        roughness=(sum(abs(b-a) for a,b in zip(differences,differences[1:]))/(max(span,1e-9)*max(1,len(differences)-1))) if len(differences)>1 else 0
        kind="elbow_angle" if "elbow_angle" in name else "normalized_distance"
        range_ok=span>=limits["minimum_range"][kind]
        coverage_ok=coverage>=limits["minimum_valid_frame_fraction"]
        roughness_ok=roughness<=limits["maximum_normalized_roughness"]
        range_score=min(1,span/(limits["minimum_range"][kind]*1.5)) if raw else 0
        smooth_score=max(0,1-roughness/limits["maximum_normalized_roughness"])
        score=.45*coverage+.35*range_score+.2*smooth_score-.01*priority
        if viewpoint=="oblique":score*=limits["oblique_confidence_multiplier"]
        if viewpoint=="unknown":score*=limits["unknown_confidence_multiplier"]
        eligible=bool(raw) and coverage_ok and range_ok and roughness_ok and score>=limits["minimum_signal_confidence"]
        ranked.append({"name":name,"priority":priority,"coverage":coverage,"range":span,"roughness":roughness,
            "selection_score":score,"eligible":eligible,"coverage_ok":coverage_ok,"range_ok":range_ok,"roughness_ok":roughness_ok})
    return sorted(ranked,key=lambda item:(not item["eligible"],-item["selection_score"],item["priority"]))


def _relevant_landmarks(signal_name:str,observable_side:str)->list[str]:
    if signal_name=="observable_elbow_angle" and observable_side in {"left","right"}:
        return [f"{observable_side}_shoulder",f"{observable_side}_elbow",f"{observable_side}_wrist"]
    if signal_name=="bilateral_elbow_angle":
        return [f"{side}_{joint}" for side in ("left","right") for joint in ("shoulder","elbow","wrist")]
    return ["left_shoulder","right_shoulder","left_wrist","right_wrist","left_hip","right_hip"]


def trace_phase_state(raw_observations:list[VideoObservation],observations:list[VideoObservation],video_summary:dict,config:dict)->tuple[list[dict],dict]:
    viewpoint=video_summary["dominant_viewpoint"]["value"];observable_side=video_summary.get("observable_anatomical_side","ambiguous")
    selected=select_phase_signal(observations,viewpoint,observable_side,config)
    ranking=rank_phase_signals(observations,viewpoint,observable_side,config)
    if selected is None:
        rows=[]
        for raw,smooth in zip(raw_observations,observations):
            rows.append({"timestamp_ms":smooth.timestamp_ms,"frame_index":smooth.frame_index,
                "predicted_viewpoint":smooth.viewpoint.value,"viewpoint_confidence":smooth.viewpoint.confidence,
                "selected_phase_signal":"","raw_phase_value":"","smoothed_phase_value":"","valid_signal":False,
                "signal_quality":"phase_signal_unavailable","top_threshold":"","bottom_threshold":"","current_state":"unavailable",
                "detected_transition":"","current_repetition_count":0,"left_elbow_angle":"","right_elbow_angle":"",
                "robust_bilateral_elbow_angle":"","normalized_shoulder_wrist_distance":"","relevant_landmark_quality":"{}",
                "quality_flags":"|".join(smooth.quality_flags)})
        return rows,{"selected_phase_signal":None,"runner_up_signals":ranking,"phase_signal_unavailable":True}
    thresholds=phase_thresholds(selected,config);limits=config["phase_segmentation"]
    signal_name=selected.name;relevant=_relevant_landmarks(signal_name,observable_side)
    state="seeking_top";top_since=start=bottom_time=bottom_value=last_valid=None
    lowering_since=bottom_since=rising_since=None;count=0
    reset_counts=Counter();transition_counts=Counter();rows=[]
    previous_value=None;top_crossings=bottom_crossings=0;time_above=time_below=0
    previous_timestamp=None
    all_viewpoint_changes={int(item["timestamp_ms"]):item for item in video_summary.get("viewpoint_changes",[])}
    viewpoint_changes={timestamp:item for timestamp,item in all_viewpoint_changes.items() if item.get("from") not in (None,"unknown")}
    for raw,smooth in zip(raw_observations,observations):
        raw_signals=candidate_signals(raw,observable_side,config) if raw.pose.detected else {}
        smooth_signals=candidate_signals(smooth,observable_side,config) if smooth.pose.detected else {}
        value=smooth_signals.get(signal_name);raw_value=raw_signals.get(signal_name)
        transition=""
        if smooth.timestamp_ms in all_viewpoint_changes and smooth.timestamp_ms not in viewpoint_changes:
            transition="viewpoint_initialized"
        if smooth.timestamp_ms in viewpoint_changes:
            state="seeking_top";top_since=start=bottom_time=bottom_value=None
            lowering_since=bottom_since=rising_since=None;last_valid=None
            reset_counts["viewpoint_change_reset"]+=1;transition="viewpoint_change_reset"
        if value is not None:
            if last_valid is not None and smooth.timestamp_ms-last_valid>limits["maximum_pose_gap_ms"]:
                state="seeking_top";top_since=start=bottom_time=bottom_value=None
                lowering_since=bottom_since=rising_since=None
                reset_counts["excessive_gap_reset"]+=1;transition="excessive_gap_reset"
            if previous_value is not None:
                if previous_value<thresholds["top"]<=value:top_crossings+=1
                if previous_value>thresholds["bottom"]>=value:bottom_crossings+=1
            if previous_timestamp is not None:
                dt=smooth.timestamp_ms-previous_timestamp
                if value>=thresholds["top"]:time_above+=dt
                if value<=thresholds["bottom"]:time_below+=dt
            last_valid=smooth.timestamp_ms;previous_value=value;previous_timestamp=smooth.timestamp_ms
            if state=="seeking_top":
                if value>=thresholds["top"]:
                    if top_since is None:top_since=smooth.timestamp_ms
                    if smooth.timestamp_ms-top_since>=limits["minimum_phase_dwell_ms"]:
                        state="top";start=top_since;transition=transition or "seeking_top_to_top";transition_counts["top_acquired"]+=1
                else:top_since=None
            elif state=="top":
                if value<thresholds["top"]-thresholds["hysteresis"]:
                    state="lowering";lowering_since=smooth.timestamp_ms;bottom_value=value;bottom_time=smooth.timestamp_ms
                    transition=transition or "top_to_lowering";transition_counts["top_to_lowering"]+=1
            elif state=="lowering":
                if bottom_value is None or value<bottom_value:bottom_value=value;bottom_time=smooth.timestamp_ms
                if value<=thresholds["bottom"] and lowering_since is not None and smooth.timestamp_ms-lowering_since>=limits["minimum_phase_dwell_ms"]:
                    state="bottom";bottom_since=smooth.timestamp_ms;transition=transition or "lowering_to_bottom";transition_counts["top_to_bottom"]+=1
                elif start is not None and smooth.timestamp_ms-start>limits["maximum_repetition_duration_ms"]:
                    state="seeking_top";top_since=start=bottom_time=bottom_value=None
                    lowering_since=bottom_since=rising_since=None;reset_counts["maximum_duration_reset"]+=1
                    transition=transition or "maximum_duration_reset"
            elif state=="bottom":
                if bottom_value is None or value<bottom_value:bottom_value=value;bottom_time=smooth.timestamp_ms
                if value>thresholds["bottom"]+thresholds["hysteresis"] and bottom_since is not None and smooth.timestamp_ms-bottom_since>=limits["minimum_phase_dwell_ms"]:
                    state="rising";rising_since=smooth.timestamp_ms;transition=transition or "bottom_to_rising";transition_counts["bottom_to_rising"]+=1
            elif state=="rising":
                if value>=thresholds["top"] and rising_since is not None and smooth.timestamp_ms-rising_since>=limits["minimum_phase_dwell_ms"]:
                    duration=smooth.timestamp_ms-start
                    transition_counts["bottom_to_top"]+=1
                    if limits["minimum_repetition_duration_ms"]<=duration<=limits["maximum_repetition_duration_ms"]:
                        count+=1;transition="completed_cycle";transition_counts["completed_cycles"]+=1
                    else:
                        transition="duration_rejected_cycle";transition_counts["duration_rejected_cycles"]+=1
                    state="top";start=smooth.timestamp_ms;top_since=smooth.timestamp_ms
                    bottom_time=bottom_value=lowering_since=bottom_since=rising_since=None
        relevant_quality={}
        for name in relevant:
            point=smooth.pose.landmarks.get(name)
            relevant_quality[name]={"visibility":point.visibility,"presence":point.presence} if point else None
        minimum_visibility=min((item["visibility"] or 0) for item in relevant_quality.values() if item) if any(relevant_quality.values()) else 0
        minimum_presence=min((item["presence"] or 0) for item in relevant_quality.values() if item) if any(relevant_quality.values()) else 0
        if value is None:signal_quality="invalid_signal"
        elif minimum_visibility<config["landmark_quality"]["minimum_visibility"] or minimum_presence<config["landmark_quality"]["minimum_presence"]:signal_quality="low_relevant_landmark_quality"
        else:signal_quality="valid"
        elbow_values=[smooth_signals.get("left_elbow_angle"),smooth_signals.get("right_elbow_angle")]
        elbow_values=[item for item in elbow_values if item is not None]
        rows.append({"timestamp_ms":smooth.timestamp_ms,"frame_index":smooth.frame_index,
            "predicted_viewpoint":smooth.viewpoint.value,"viewpoint_confidence":smooth.viewpoint.confidence,
            "selected_phase_signal":signal_name,"raw_phase_value":raw_value if raw_value is not None else "",
            "smoothed_phase_value":value if value is not None else "","valid_signal":value is not None,"signal_quality":signal_quality,
            "top_threshold":thresholds["top"],"bottom_threshold":thresholds["bottom"],"current_state":state,
            "detected_transition":transition,"current_repetition_count":count,
            "left_elbow_angle":smooth_signals.get("left_elbow_angle") if smooth_signals.get("left_elbow_angle") is not None else "",
            "right_elbow_angle":smooth_signals.get("right_elbow_angle") if smooth_signals.get("right_elbow_angle") is not None else "",
            "robust_bilateral_elbow_angle":statistics.median(elbow_values) if elbow_values else "",
            "normalized_shoulder_wrist_distance":smooth_signals.get("mid_shoulder_to_wrists") if smooth_signals.get("mid_shoulder_to_wrists") is not None else "",
            "relevant_landmark_quality":json.dumps(relevant_quality,separators=(",",":"),sort_keys=True),
            "quality_flags":"|".join(smooth.quality_flags)})
    ending_incomplete=state in {"lowering","bottom","rising"}
    summary={"selected_phase_signal":signal_name,"signal_range":selected.range_of_motion,"signal_coverage":selected.coverage,
        "signal_roughness":selected.roughness,"selection_score":selected.confidence,"thresholds":thresholds,
        "time_above_top_seconds":time_above/1000,"time_below_bottom_seconds":time_below/1000,
        "top_crossings":top_crossings,"bottom_crossings":bottom_crossings,"completed_cycles":count,
        "top_to_bottom_transitions":transition_counts["top_to_bottom"],"bottom_to_top_transitions":transition_counts["bottom_to_top"],
        "duration_rejected_cycles":transition_counts["duration_rejected_cycles"],"ending_incomplete_cycle":ending_incomplete,
        "phase_state_resets":sum(reset_counts.values()),"viewpoint_change_resets":reset_counts["viewpoint_change_reset"],
        "excessive_gap_resets":reset_counts["excessive_gap_reset"],"maximum_duration_resets":reset_counts["maximum_duration_reset"],
        "runner_up_signals":[item for item in ranking if item["name"]!=signal_name],"signal_ranking":ranking}
    return rows,summary
