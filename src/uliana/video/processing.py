from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

from uliana.contracts.models import VideoObservation, ViewpointEstimate
from uliana.video.geometry import pixel_distance, torso_length
from .landmark_quality import assess_landmark_quality
from .smoothing import LandmarkSmoother
from .viewpoint import ViewpointTracker, classify_viewpoint, summarize_viewpoints


def _jitter(observations: list[VideoObservation], raw: bool) -> float | None:
    values=[]
    for previous,current in zip(observations,observations[1:]):
        a=previous.pose.raw_landmarks if raw else previous.pose.landmarks
        b=current.pose.raw_landmarks if raw else current.pose.landmarks
        if not a or not b: continue
        scale=torso_length(b,current.image_width_px,current.image_height_px)
        if not scale: continue
        for name in set(a)&set(b): values.append(pixel_distance(a[name],b[name],current.image_width_px,current.image_height_px)/scale)
    return sum(values)/len(values) if values else None


def process_observations(raw_observations: list[VideoObservation], config: dict) -> tuple[list[VideoObservation],dict]:
    smoother=LandmarkSmoother(config); tracker=ViewpointTracker(config["viewpoint"]["minimum_dwell_ms"])
    output=[]; evidences=[]; quality_counts=Counter(); availability=defaultdict(list); previous=None; previous_scale=None
    for raw in raw_observations:
        smoothed=smoother.process(raw)
        quality=assess_landmark_quality(smoothed,config,previous,previous_scale)
        evidence=classify_viewpoint(smoothed,config); evidences.append(evidence)
        stable=tracker.update(evidence)
        codes=list(dict.fromkeys(smoothed.quality_flags+quality.codes+(["insufficient_viewpoint_evidence"] if evidence.label=="unknown" else [])))
        quality_counts.update(codes)
        for group,value in quality.group_available.items(): availability[group].append(value)
        confidence=evidence.confidence if stable==evidence.label else None
        output.append(replace(smoothed,viewpoint=ViewpointEstimate(stable,confidence,evidence.reason),quality_flags=codes))
        if smoothed.pose.detected: previous=smoothed; previous_scale=quality.torso_scale_px or previous_scale
    aggregate=summarize_viewpoints(evidences,config); viewpoint=aggregate["viewpoint"]
    capabilities=config["capability_matrix"][viewpoint.value]
    warnings=[]
    if viewpoint.value=="unknown": warnings.append("insufficient_viewpoint_evidence")
    if any("excessive_pose_gap" in item.quality_flags for item in output): warnings.append("excessive_pose_gap")
    detected=sum(item.pose.detected for item in output)/len(output) if output else 0
    summary={"dominant_viewpoint":viewpoint.to_dict(),"observable_anatomical_side":aggregate["observable_side"],
        "viewpoint_changes":tracker.changes,"valid_viewpoint_frame_fraction":aggregate["valid_frame_fraction"],
        "valid_pose_fraction":detected,"landmark_availability_by_region":{k:sum(v)/len(v) if v else 0 for k,v in availability.items()},
        "quality_code_counts":dict(quality_counts),"jitter":{ "raw_mean_normalized_displacement":_jitter(output,True),
        "smoothed_mean_normalized_displacement":_jitter(output,False)},"capabilities":capabilities,"warnings":warnings,
        "one_person_assumption":True}
    return output,summary


def write_observations(path: Path, observations: list[VideoObservation]) -> None:
    with path.open("w",encoding="utf-8") as handle:
        for observation in observations: handle.write(json.dumps(observation.to_dict(),separators=(",",":"),allow_nan=False)+"\n")


def observation_from_dict(value:dict)->VideoObservation:
    from uliana.contracts.models import LandmarkObservation,PoseObservation
    pose=value["pose"]
    convert=lambda points:{name:LandmarkObservation(**point) for name,point in (points or {}).items()} if points is not None else None
    return VideoObservation(value["schema_version"],value["session_id"],value["frame_index"],value["timestamp_ms"],value["timestamp_source"],
        value["fps"],value["image_width_px"],value["image_height_px"],PoseObservation(pose["detected"],convert(pose["landmarks"]) or {},pose.get("model_confidence"),
        convert(pose.get("raw_landmarks")),convert(pose.get("world_landmarks")),pose.get("world_landmarks_caveat")),ViewpointEstimate(**value["viewpoint"]),value.get("quality_flags",[]))


def render_diagnostic_video(video_path: Path, destination: Path, observations: list[VideoObservation], summary: dict) -> None:
    try: import cv2
    except ImportError as exc: raise RuntimeError("video extras are required") from exc
    capture=cv2.VideoCapture(str(video_path))
    if not capture.isOpened(): raise ValueError(f"cannot open video: {video_path}")
    width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)); height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)); fps=float(capture.get(cv2.CAP_PROP_FPS)) or 30
    writer=cv2.VideoWriter(str(destination),cv2.VideoWriter_fourcc(*"mp4v"),fps,(width,height))
    connections=(("left_shoulder","left_elbow"),("left_elbow","left_wrist"),("right_shoulder","right_elbow"),("right_elbow","right_wrist"),("left_shoulder","left_hip"),("right_shoulder","right_hip"),("left_hip","left_ankle"),("right_hip","right_ankle"))
    try:
        index=0
        while index<len(observations):
            ok,image=capture.read()
            if not ok: break
            observation=observations[index]; landmarks=observation.pose.landmarks
            for first,second in connections:
                if first in landmarks and second in landmarks:
                    a,b=landmarks[first],landmarks[second]
                    cv2.line(image,(round(a.x*width),round(a.y*height)),(round(b.x*width),round(b.y*height)),(80,220,160),2)
            quality="OK" if not observation.quality_flags else observation.quality_flags[0]
            text=f"{observation.viewpoint.value} {observation.viewpoint.confidence or 0:.2f} | side {summary['observable_anatomical_side']}"
            cv2.putText(image,text,(18,30),cv2.FONT_HERSHEY_SIMPLEX,.6,(70,220,150),2)
            cv2.putText(image,f"t={observation.timestamp_ms} ms | {quality}",(18,58),cv2.FONT_HERSHEY_SIMPLEX,.55,(80,80,255) if observation.quality_flags else (220,220,220),2)
            cv2.putText(image,"MONOCULAR DIAGNOSTIC - NOT 3D/360",(18,height-18),cv2.FONT_HERSHEY_SIMPLEX,.5,(50,190,255),1)
            writer.write(image); index+=1
    finally: capture.release(); writer.release()
