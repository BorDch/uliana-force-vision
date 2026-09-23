#!/usr/bin/env python3
from __future__ import annotations

import argparse,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from uliana.config import load_config
from uliana.contracts.validation import validate_contract
from uliana.video.camera_session import analyze_camera_observations,render_camera_video,write_camera_outputs
from uliana.video.processing import observation_from_dict


def main()->int:
    parser=argparse.ArgumentParser(description="Produce a reliability-gated camera-only push-up SessionResult.")
    parser.add_argument("--video-observations",required=True,type=Path);parser.add_argument("--video-summary",required=True,type=Path)
    parser.add_argument("--output-dir",required=True,type=Path);parser.add_argument("--video",type=Path,help="Optional source video for annotation")
    parser.add_argument("--config",type=Path,default=ROOT/"configs/video_processing.json");parser.add_argument("--json",action="store_true")
    args=parser.parse_args();config=load_config(args.config)
    observations=[observation_from_dict(json.loads(line)) for line in args.video_observations.read_text(encoding="utf-8").splitlines() if line.strip()]
    summary=json.loads(args.video_summary.read_text(encoding="utf-8"));result,features,phases,metrics=analyze_camera_observations(observations,summary,config)
    validate_contract("session_result",result);write_camera_outputs(args.output_dir,result,features,metrics)
    overlay=None
    if args.video:overlay=args.output_dir/"camera_annotated.mp4";render_camera_video(args.video,overlay,observations,result,phases)
    payload={"session_id":result.session_id,"repetition_count":result.repetition_count,"count_confidence":metrics["count_confidence"],
        "selected_phase_signal":result.provenance["phase_signal"],"viewpoint":result.detected_viewpoint.to_dict(),
        "assessment_coverage":result.overall_assessment_coverage,"available_assessments":sum(a.result!="unavailable" for a in result.assessments),
        "unavailable_assessments":[{"condition":a.condition,"rep_id":a.rep_id,"reason":a.reason} for a in result.unavailable_assessments],
        "quality_investigation":{"quality_code_counts":summary.get("quality_code_counts",{}),"affected_landmark_groups":{k:v for k,v in summary.get("landmark_availability_by_region",{}).items() if v<1},
        "phase_landmarks_usable":result.provenance["phase_signal"] is not None,"threshold_note":"Quality thresholds remain provisional and were not lowered to force availability."},
        "session_result":str(args.output_dir/"session_result.json"),"annotated_video":str(overlay) if overlay else None}
    print(json.dumps(payload,indent=2,allow_nan=False) if args.json else "\n".join((f"Session: {result.session_id}",f"Repetitions: {result.repetition_count} (confidence {metrics['count_confidence']:.3f})",f"Phase signal: {result.provenance['phase_signal'] or 'unavailable'}",f"Viewpoint: {result.detected_viewpoint.value}",f"Assessment coverage: {result.overall_assessment_coverage:.1%}",f"Unavailable: {payload['unavailable_assessments']}",f"Session result: {payload['session_result']}")))
    return 0


if __name__=="__main__":raise SystemExit(main())
