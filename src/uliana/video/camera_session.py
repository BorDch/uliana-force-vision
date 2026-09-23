from __future__ import annotations

import json
from dataclasses import asdict,replace
from pathlib import Path

from uliana.contracts.models import SessionResult,SynchronizationReport,VideoObservation,ViewpointEstimate
from uliana.fusion.assessments import assess_body_alignment,assess_depth_proxy
from .features import extract_repetition_features
from .phases import segment_by_viewpoint


def analyze_camera_observations(observations:list[VideoObservation],video_summary:dict,config:dict)->tuple[SessionResult,list[dict],dict[int,str],dict]:
    view=video_summary["dominant_viewpoint"]; viewpoint=view["value"]; view_confidence=view.get("confidence")
    side=video_summary.get("observable_anatomical_side","ambiguous")
    segmentation=segment_by_viewpoint(observations,viewpoint,side,config)
    assessments=[];features=[]
    if segmentation.selected_signal is not None:
        for interval in segmentation.intervals:
            item=replace(extract_repetition_features(observations,interval,side,config),viewpoint=viewpoint,viewpoint_confidence=view_confidence)
            features.append(asdict(item));phase_confidence=interval.confidence or 0
            assessments.extend((assess_body_alignment(item,phase_confidence,config),assess_depth_proxy(item,phase_confidence,config)))
    unavailable=[item for item in assessments if item.result=="unavailable"]
    eligible=len(assessments);answered=eligible-len(unavailable);coverage=answered/eligible if eligible else 0
    warnings=list(dict.fromkeys(video_summary.get("warnings",[])+segmentation.warnings))
    if segmentation.selected_signal is None:warnings.append("repetition_count_unavailable")
    result=SessionResult("1.0",observations[0].session_id if observations else "unknown","camera_only",
        len(segmentation.intervals) if segmentation.selected_signal is not None else None,segmentation.intervals,
        ViewpointEstimate(viewpoint,view_confidence,view.get("reason")),assessments,None,SynchronizationReport("not_applicable",reason="camera_only_session"),
        coverage,warnings,unavailable,video_summary.get("viewpoint_changes",[]),{"pipeline":"camera_milestone_4",
        "phase_signal":segmentation.selected_signal.name if segmentation.selected_signal else None,"experimental_configuration":config})
    reasons=sorted({item.reason for item in unavailable if item.reason})
    metrics={"count_confidence":sum((item.confidence or 0) for item in segmentation.intervals)/len(segmentation.intervals) if segmentation.intervals else 0,
        "phase_signal_coverage":segmentation.selected_signal.coverage if segmentation.selected_signal else 0,
        "eligible_assessments":eligible,"answered_assessments":answered,"assessment_coverage":coverage,
        "abstention_rate":len(unavailable)/eligible if eligible else 0,"unavailable_reason_distribution":{reason:sum(item.reason==reason for item in unavailable) for reason in reasons}}
    return result,features,segmentation.frame_phases,metrics


def write_camera_outputs(output_dir:Path,result:SessionResult,features:list[dict],metrics:dict)->None:
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/"session_result.json").write_text(json.dumps(result.to_dict(),indent=2,allow_nan=False)+"\n",encoding="utf-8")
    (output_dir/"camera_repetition_features.json").write_text(json.dumps(features,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    (output_dir/"camera_metrics.json").write_text(json.dumps(metrics,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def render_camera_video(video_path:Path,destination:Path,observations:list[VideoObservation],result:SessionResult,phases:dict[int,str],debug:bool=False)->None:
    try:import cv2
    except ImportError as exc:raise RuntimeError("video extras are required") from exc
    capture=cv2.VideoCapture(str(video_path));width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT));fps=float(capture.get(cv2.CAP_PROP_FPS)) or 30
    writer=cv2.VideoWriter(str(destination),cv2.VideoWriter_fourcc(*"mp4v"),fps,(width,height));connections=(("left_shoulder","left_elbow"),("left_elbow","left_wrist"),("right_shoulder","right_elbow"),("right_elbow","right_wrist"),("left_shoulder","left_hip"),("right_shoulder","right_hip"),("left_hip","left_ankle"),("right_hip","right_ankle"))
    assessments={}
    for assessment in result.assessments:assessments.setdefault(assessment.rep_id,[]).append(assessment)
    try:
        for observation in observations:
            ok,image=capture.read()
            if not ok:break
            lm=observation.pose.landmarks
            for a,b in connections:
                if a in lm and b in lm:cv2.line(image,(round(lm[a].x*width),round(lm[a].y*height)),(round(lm[b].x*width),round(lm[b].y*height)),(80,220,160),2)
            active=next((interval for interval in result.repetition_intervals if interval.start_ms<=observation.timestamp_ms<=interval.end_ms),None)
            rep=active.rep_id if active else sum(interval.end_ms<observation.timestamp_ms for interval in result.repetition_intervals)
            cue="Assessment unavailable"
            if active:
                available=[a for a in assessments.get(active.rep_id,[]) if a.result!="unavailable"]
                if any(a.condition=="body_alignment_deviation" and a.result=="condition_detected" for a in available):cue="Keep the body line stable"
                elif any(a.condition=="push_up_depth_proxy" and a.result=="condition_detected" for a in available):cue="Increase the measured range"
                elif available:cue="Measured conditions adequate"
                elif any(a.condition=="push_up_depth_proxy" for a in assessments.get(active.rep_id,[])):cue="Depth assessment unavailable from this view"
            lines=[f"Rep {rep}"]
            if active and cue not in {"Assessment unavailable", "Measured conditions adequate"}: lines.append(cue)
            if debug:
                phase=phases.get(observation.timestamp_ms,"unknown"); signal=active.selected_phase_signal if active else result.provenance.get("phase_signal")
                lines.extend([f"phase {phase}",f"signal {signal or 'unavailable'}"])
            for index,text in enumerate(lines):cv2.putText(image,text,(18,34+index*30),cv2.FONT_HERSHEY_SIMPLEX,.7,(70,220,150),2)
            writer.write(image)
    finally:capture.release();writer.release()
