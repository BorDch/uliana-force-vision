from __future__ import annotations

import math
from dataclasses import dataclass

from uliana.contracts.models import RepetitionInterval, VideoObservation
from .geometry import pixel_distance,torso_length
from .phases import candidate_signals


@dataclass(frozen=True)
class RepetitionCameraFeatures:
    rep_id:int; start_ms:int; bottom_ms:int|None; end_ms:int; duration_ms:int
    lowering_duration_ms:int|None; rising_duration_ms:int|None; selected_phase_signal:str|None
    phase_signal_range:float|None; minimum_elbow_angle_deg:float|None
    minimum_left_elbow_angle_deg:float|None; minimum_right_elbow_angle_deg:float|None
    elbow_angles:list[tuple[int,float]]
    alignment_angle_deviation_deg:list[tuple[int,float]]
    normalized_hip_displacement:list[tuple[int,float]]
    signed_hip_displacement:list[tuple[int,float]]
    valid_frame_fraction:float; landmark_quality_summary:dict[str,float]
    viewpoint:str; viewpoint_confidence:float|None; frame_count:int


def _alignment(observation:VideoObservation,side:str,config:dict):
    lm=observation.pose.landmarks; names=[f"{side}_shoulder",f"{side}_hip",f"{side}_ankle"]
    if any(name not in lm for name in names):return None
    points=[lm[name] for name in names]; limits=config["landmark_quality"]
    if any((point.visibility or 0)<limits["minimum_visibility"] or (point.presence or 0)<limits["minimum_presence"] for point in points):return None
    width,height=observation.image_width_px,observation.image_height_px
    shoulder,hip,ankle=points; ax,ay=shoulder.x*width,shoulder.y*height; bx,by=ankle.x*width,ankle.y*height; px,py=hip.x*width,hip.y*height
    vx,vy=bx-ax,by-ay; length=math.hypot(vx,vy)
    if length<=1:return None
    signed=((vx*(py-ay)-vy*(px-ax))/length); normalized=signed/length
    projection=((px-ax)*vx+(py-ay)*vy)/(length*length); qx,qy=ax+projection*vx,ay+projection*vy
    perpendicular=math.hypot(px-qx,py-qy)/length
    u=(ax-px,ay-py);v=(bx-px,by-py);den=math.hypot(*u)*math.hypot(*v)
    angle=abs(180-math.degrees(math.acos(max(-1,min(1,(u[0]*v[0]+u[1]*v[1])/den))))) if den>1e-9 else None
    return angle,perpendicular,normalized


def extract_repetition_features(observations:list[VideoObservation],interval:RepetitionInterval,observable_side:str,config:dict)->RepetitionCameraFeatures:
    frames=[item for item in observations if interval.start_ms<=item.timestamp_ms<=interval.end_ms]
    signals=[candidate_signals(item,observable_side,config) for item in frames]
    left=[value["left_elbow_angle"] for value in signals if value["left_elbow_angle"] is not None]
    right=[value["right_elbow_angle"] for value in signals if value["right_elbow_angle"] is not None]
    combined=left+right; selected=[value.get(interval.selected_phase_signal) for value in signals if interval.selected_phase_signal and value.get(interval.selected_phase_signal) is not None]
    side=observable_side if observable_side in ("left","right") else None
    alignment=[]
    if side:
        for frame in frames:
            value=_alignment(frame,side,config)
            if value:alignment.append((frame.timestamp_ms,*value))
    valid=sum(frame.pose.detected for frame in frames)/len(frames) if frames else 0
    quality={code:sum(code in frame.quality_flags for frame in frames)/len(frames) for code in sorted({code for frame in frames for code in frame.quality_flags})} if frames else {}
    view_conf=[frame.viewpoint.confidence for frame in frames if frame.viewpoint.confidence is not None]
    bottom=interval.bottom_ms
    return RepetitionCameraFeatures(interval.rep_id,interval.start_ms,bottom,interval.end_ms,interval.end_ms-interval.start_ms,
        bottom-interval.start_ms if bottom is not None else None,interval.end_ms-bottom if bottom is not None else None,
        interval.selected_phase_signal,max(selected)-min(selected) if selected else None,min(combined) if combined else None,
        min(left) if left else None,min(right) if right else None,
        [(frame.timestamp_ms,value["observable_elbow_angle"] if value["observable_elbow_angle"] is not None else value["bilateral_elbow_angle"]) for frame,value in zip(frames,signals) if value["observable_elbow_angle"] is not None or value["bilateral_elbow_angle"] is not None],
        [(t,a) for t,a,_,_ in alignment],[(t,p) for t,_,p,_ in alignment],
        [(t,s) for t,_,_,s in alignment],valid,quality,frames[-1].viewpoint.value if frames else "unknown",
        sum(view_conf)/len(view_conf) if view_conf else None,len(frames))
