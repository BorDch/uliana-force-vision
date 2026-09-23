from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from uliana.contracts.models import LandmarkObservation, VideoObservation, ViewpointEstimate
from .geometry import axis_angle, pixel_distance, torso_length


@dataclass(frozen=True)
class ViewpointFrameEvidence:
    timestamp_ms: int
    label: str
    confidence: float
    reason: str
    features: dict[str, float | None]
    observable_side: str


def _quality(point: LandmarkObservation) -> float: return min(point.visibility or 0, point.presence or 0)


def classify_viewpoint(observation: VideoObservation, config: dict) -> ViewpointFrameEvidence:
    lm=observation.pose.landmarks; required=("left_shoulder","right_shoulder","left_hip","right_hip")
    if not observation.pose.detected or any(name not in lm for name in required):
        return ViewpointFrameEvidence(observation.timestamp_ms,"unknown",0,"insufficient_viewpoint_evidence",{},"ambiguous")
    width,height=observation.image_width_px,observation.image_height_px; torso=torso_length(lm,width,height)
    if not torso or torso <= 1:
        return ViewpointFrameEvidence(observation.timestamp_ms,"unknown",0,"insufficient_viewpoint_evidence",{},"ambiguous")
    shoulder=pixel_distance(lm["left_shoulder"],lm["right_shoulder"],width,height)/torso
    hip=pixel_distance(lm["left_hip"],lm["right_hip"],width,height)/torso
    left_names=[name for name in ("left_shoulder","left_elbow","left_wrist","left_hip","left_ankle") if name in lm]
    right_names=[name for name in ("right_shoulder","right_elbow","right_wrist","right_hip","right_ankle") if name in lm]
    left=sum(_quality(lm[name]) for name in left_names)/len(left_names)
    right=sum(_quality(lm[name]) for name in right_names)/len(right_names)
    visibility_difference=abs(left-right)
    z_values=[lm[name].z for name in required]
    depth_difference=(abs(lm["left_shoulder"].z-lm["right_shoulder"].z)+abs(lm["left_hip"].z-lm["right_hip"].z))/2 if all(z is not None for z in z_values) else None
    features={"shoulder_width_torso_ratio":shoulder,"hip_width_torso_ratio":hip,"side_visibility_difference":visibility_difference,
              "depth_difference":depth_difference,"shoulder_axis_deg":axis_angle(lm["left_shoulder"],lm["right_shoulder"],width,height),
              "hip_axis_deg":axis_angle(lm["left_hip"],lm["right_hip"],width,height),"body_scale_px":torso}
    limits=config["viewpoint"]; width_ratio=(shoulder+hip)/2
    side_width=width_ratio <= limits["side_width_ratio_max"]; side_visibility=visibility_difference >= limits["side_visibility_difference_min"]
    side_depth=depth_difference is not None and depth_difference >= limits["side_depth_difference_min"]
    front_width=width_ratio >= limits["front_width_ratio_min"]; front_visibility=visibility_difference <= limits["front_visibility_difference_max"]
    front_depth=depth_difference is None or depth_difference <= limits["front_depth_difference_max"]
    if side_width and (side_visibility or side_depth):
        label="side"; confidence=min(1,.6+max(0,limits["front_width_ratio_min"]-width_ratio)+(depth_difference or 0)); reason="narrow_projection_with_visibility_or_depth_separation"
    elif front_width and front_visibility and front_depth: label="front"; confidence=min(1,.55+(width_ratio-limits["front_width_ratio_min"])+(limits["front_visibility_difference_max"]-visibility_difference)); reason="wide_projection_and_balanced_side_evidence"
    elif not side_width and not front_width:
        label="oblique"; confidence=min(.85,.6+abs(width_ratio-(limits["side_width_ratio_max"]+limits["front_width_ratio_min"])/2)); reason="intermediate_projected_body_width"
    else: label="unknown"; confidence=.25; reason="conflicting_or_weak_viewpoint_evidence"
    if confidence < limits["minimum_frame_confidence"]: label="unknown"; reason="insufficient_viewpoint_evidence"
    margin=limits["side_selection_minimum_margin"]
    observable="left" if left>right+margin else "right" if right>left+margin else "ambiguous"
    return ViewpointFrameEvidence(observation.timestamp_ms,label,confidence,reason,features,observable)


class ViewpointTracker:
    def __init__(self, minimum_dwell_ms: int):
        self.minimum_dwell_ms=minimum_dwell_ms; self.current="unknown"; self.candidate=None; self.candidate_since=None; self.changes=[]
    def update(self,evidence:ViewpointFrameEvidence)->str:
        if evidence.label=="unknown" or evidence.label==self.current: self.candidate=None; self.candidate_since=None; return self.current
        if evidence.label!=self.candidate: self.candidate=evidence.label; self.candidate_since=evidence.timestamp_ms; return self.current
        if evidence.timestamp_ms-self.candidate_since>=self.minimum_dwell_ms:
            old=self.current; self.current=self.candidate; self.changes.append({"timestamp_ms":evidence.timestamp_ms,"from":old,"to":self.current})
            self.candidate=None; self.candidate_since=None
        return self.current


def summarize_viewpoints(evidence: list[ViewpointFrameEvidence], config: dict) -> dict:
    valid=[item for item in evidence if item.label!="unknown"]
    fraction=len(valid)/len(evidence) if evidence else 0
    if not valid or fraction<config["viewpoint"]["minimum_valid_frame_fraction"]:
        return {"viewpoint":ViewpointEstimate("unknown",0,"insufficient_viewpoint_evidence"),"observable_side":"ambiguous","valid_frame_fraction":fraction}
    counts=Counter(item.label for item in valid); label,count=counts.most_common(1)[0]
    if len(counts)>1 and count/len(valid)<.6:
        return {"viewpoint":ViewpointEstimate("unknown",count/len(valid),"contradictory_session_evidence"),"observable_side":"ambiguous","valid_frame_fraction":fraction}
    selected=[item for item in valid if item.label==label]; confidence=sum(item.confidence for item in selected)/len(selected)*count/len(valid)
    sides=Counter(item.observable_side for item in selected if item.observable_side!="ambiguous")
    side=sides.most_common(1)[0][0] if sides and sides.most_common(1)[0][1]/len(selected)>=.6 else "ambiguous"
    return {"viewpoint":ViewpointEstimate(label,confidence,"dominant_valid_frame_evidence"),"observable_side":side,"valid_frame_fraction":fraction}
