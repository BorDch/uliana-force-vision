from __future__ import annotations

import math
from dataclasses import dataclass

from uliana.contracts.models import RepetitionInterval, VideoObservation
from .geometry import midpoint, pixel_distance, torso_length


def _angle(a, b, c, width, height):
    u=((a.x-b.x)*width,(a.y-b.y)*height); v=((c.x-b.x)*width,(c.y-b.y)*height)
    denominator=math.hypot(*u)*math.hypot(*v)
    if denominator<=1e-9:return None
    return math.degrees(math.acos(max(-1,min(1,(u[0]*v[0]+u[1]*v[1])/denominator))))


def candidate_signals(observation:VideoObservation,observable_side:str="ambiguous",config:dict|None=None)->dict[str,float|None]:
    lm=observation.pose.landmarks; width,height=observation.image_width_px,observation.image_height_px
    limits=(config or {}).get("landmark_quality",{})
    def valid(name):
        if name not in lm:return False
        return ((lm[name].visibility if lm[name].visibility is not None else 0)>=limits.get("minimum_visibility",0) and
                (lm[name].presence if lm[name].presence is not None else 0)>=limits.get("minimum_presence",0))
    values={"left_elbow_angle":None,"right_elbow_angle":None,"bilateral_elbow_angle":None,
            "observable_elbow_angle":None,"shoulder_to_wrist_normalized":None,"mid_shoulder_to_wrists":None,
            "mid_shoulder_vertical_to_wrists":None,"torso_vertical_displacement":None}
    for side in ("left","right"):
        names=(f"{side}_shoulder",f"{side}_elbow",f"{side}_wrist")
        if all(valid(name) for name in names): values[f"{side}_elbow_angle"]=_angle(*(lm[name] for name in names),width,height)
    elbows=[values[name] for name in ("left_elbow_angle","right_elbow_angle") if values[name] is not None]
    if elbows: values["bilateral_elbow_angle"]=sum(elbows)/len(elbows)
    if observable_side in ("left","right"): values["observable_elbow_angle"]=values[f"{observable_side}_elbow_angle"]
    scale=torso_length(lm,width,height) if all(valid(name) for name in ("left_shoulder","right_shoulder","left_hip","right_hip")) else None
    if scale:
        side_distances=[pixel_distance(lm[f"{side}_shoulder"],lm[f"{side}_wrist"],width,height)/scale for side in ("left","right") if valid(f"{side}_shoulder") and valid(f"{side}_wrist")]
        if side_distances: values["shoulder_to_wrist_normalized"]=sum(side_distances)/len(side_distances)
        if all(valid(name) for name in ("left_shoulder","right_shoulder","left_wrist","right_wrist")):
            shoulders=midpoint(lm["left_shoulder"],lm["right_shoulder"]); wrists=midpoint(lm["left_wrist"],lm["right_wrist"])
            values["mid_shoulder_to_wrists"]=math.hypot((shoulders[0]-wrists[0])*width,(shoulders[1]-wrists[1])*height)/scale
            values["mid_shoulder_vertical_to_wrists"]=(wrists[1]-shoulders[1])*height/scale
    return values


@dataclass(frozen=True)
class SelectedSignal:
    name:str
    values:list[tuple[int,float]]
    coverage:float
    range_of_motion:float
    roughness:float
    confidence:float


@dataclass(frozen=True)
class PhaseSegmentationResult:
    intervals:list[RepetitionInterval]
    selected_signal:SelectedSignal|None
    frame_phases:dict[int,str]
    warnings:list[str]


def _quantile(values:list[float],fraction:float)->float:
    ordered=sorted(values);position=(len(ordered)-1)*fraction;lower=int(position);upper=min(lower+1,len(ordered)-1)
    return ordered[lower]+(ordered[upper]-ordered[lower])*(position-lower)


def phase_thresholds(selected:SelectedSignal,config:dict)->dict[str,float]:
    limits=config["phase_segmentation"];raw=[value for _,value in selected.values]
    quantiles=limits.get("threshold_quantiles")
    if quantiles:
        low=_quantile(raw,float(quantiles["lower"]));high=_quantile(raw,float(quantiles["upper"]))
    else:
        low=min(raw);high=max(raw)
    span=high-low
    return {"range_low":low,"range_high":high,"range":span,
        "top":low+limits["top_fraction"]*span,"bottom":low+limits["bottom_fraction"]*span,
        "hysteresis":limits["hysteresis_fraction"]*span}


def select_phase_signal(observations:list[VideoObservation],viewpoint:str,observable_side:str,config:dict)->SelectedSignal|None:
    limits=config["phase_segmentation"]; candidates=limits["candidates"][viewpoint]
    frame_values=[candidate_signals(item,observable_side,config) if item.pose.detected else {} for item in observations]
    best=None
    for priority,name in enumerate(candidates):
        values=[(item.timestamp_ms,signals.get(name)) for item,signals in zip(observations,frame_values) if signals.get(name) is not None]
        coverage=len(values)/len(observations) if observations else 0
        if not values or coverage<limits["minimum_valid_frame_fraction"]:continue
        raw=[value for _,value in values]; span=max(raw)-min(raw)
        kind="elbow_angle" if "elbow_angle" in name else "normalized_distance"
        if span<limits["minimum_range"][kind]:continue
        differences=[b-a for a,b in zip(raw,raw[1:])]
        roughness=(sum(abs(b-a) for a,b in zip(differences,differences[1:]))/(max(span,1e-9)*max(1,len(differences)-1))) if len(differences)>1 else 0
        if roughness>limits["maximum_normalized_roughness"]:continue
        range_score=min(1,span/(limits["minimum_range"][kind]*1.5)); smooth_score=max(0,1-roughness/limits["maximum_normalized_roughness"])
        confidence=.45*coverage+.35*range_score+.2*smooth_score-.01*priority
        if viewpoint=="oblique":confidence*=limits["oblique_confidence_multiplier"]
        if viewpoint=="unknown":confidence*=limits["unknown_confidence_multiplier"]
        candidate=SelectedSignal(name,[(t,v) for t,v in values],coverage,span,roughness,confidence)
        if confidence>=limits["minimum_signal_confidence"] and (best is None or confidence>best.confidence):best=candidate
    return best


def segment_repetitions(observations:list[VideoObservation],viewpoint:str,observable_side:str,config:dict,
                        rep_id_start:int=1)->PhaseSegmentationResult:
    limits=config["phase_segmentation"]; selected=select_phase_signal(observations,viewpoint,observable_side,config)
    if selected is None:return PhaseSegmentationResult([],None,{},["phase_signal_unavailable"])
    thresholds=phase_thresholds(selected,config);top=thresholds["top"];bottom=thresholds["bottom"];hysteresis=thresholds["hysteresis"]
    state="seeking_top"; phases={}; intervals=[]; top_since=start=bottom_time=last_time=None; bottom_value=None
    lowering_since=bottom_since=rising_since=None
    for timestamp,value in selected.values:
        if last_time is not None and timestamp-last_time>limits["maximum_pose_gap_ms"]:
            state="seeking_top"; top_since=start=bottom_time=bottom_value=None
            lowering_since=bottom_since=rising_since=None
        last_time=timestamp; phases[timestamp]={"seeking_top":"unknown","top":"top","lowering":"lowering","bottom":"bottom","rising":"rising"}[state]
        if state=="seeking_top":
            if value>=top:
                if top_since is None:
                    top_since=timestamp
                if timestamp-top_since>=limits["minimum_phase_dwell_ms"]:
                    state="top"
                    start=top_since
            else:
                top_since=None
        elif state=="top":
            if value<top-hysteresis:
                state="lowering"
                lowering_since=timestamp
                bottom_value=value
                bottom_time=timestamp
        elif state=="lowering":
            if bottom_value is None or value<bottom_value:
                bottom_value=value
                bottom_time=timestamp
            if value<=bottom and lowering_since is not None and timestamp-lowering_since>=limits["minimum_phase_dwell_ms"]:
                state="bottom"
                bottom_since=timestamp
            elif start is not None and timestamp-start>limits["maximum_repetition_duration_ms"]:
                state="seeking_top"
                top_since=start=bottom_time=bottom_value=None
                lowering_since=bottom_since=rising_since=None
        elif state=="bottom":
            if value<bottom_value:
                bottom_value=value
                bottom_time=timestamp
            if value>bottom+hysteresis and bottom_since is not None and timestamp-bottom_since>=limits["minimum_phase_dwell_ms"]:
                state="rising"
                rising_since=timestamp
        elif state=="rising":
            if value>=top and rising_since is not None and timestamp-rising_since>=limits["minimum_phase_dwell_ms"]:
                    duration=timestamp-start
                    if limits["minimum_repetition_duration_ms"]<=duration<=limits["maximum_repetition_duration_ms"]:
                        confidence=min(.95,selected.confidence*.9+.05)
                        intervals.append(RepetitionInterval(rep_id_start+len(intervals),start,bottom_time,timestamp,confidence,selected.name,[]))
                    state="top"
                    start=timestamp
                    top_since=timestamp
                    bottom_time=bottom_value=None
                    lowering_since=bottom_since=rising_since=None
    warnings=[]
    if state in ("lowering","bottom","rising"):warnings.append("incomplete_repetition_discarded")
    return PhaseSegmentationResult(intervals,selected,phases,warnings)


def segment_by_viewpoint(observations:list[VideoObservation],dominant_viewpoint:str,observable_side:str,config:dict)->PhaseSegmentationResult:
    # A session with no reported changes uses the aggregated viewpoint for its complete timeline.
    labels={item.viewpoint.value for item in observations if item.viewpoint.value!="unknown"}
    if len(labels)<=1:return segment_repetitions(observations,dominant_viewpoint,observable_side,config)
    intervals=[];phases={};warnings=["viewpoint_change_reset_phase_state"];selected=None;start=0
    while start<len(observations):
        label=observations[start].viewpoint.value;end=start+1
        while end<len(observations) and observations[end].viewpoint.value==label:end+=1
        result=segment_repetitions(observations[start:end],label,observable_side if label=="side" else "ambiguous",config,len(intervals)+1)
        intervals.extend(result.intervals);phases.update(result.frame_phases);warnings.extend(result.warnings);selected=selected or result.selected_signal;start=end
    return PhaseSegmentationResult(intervals,selected,phases,list(dict.fromkeys(warnings)))
