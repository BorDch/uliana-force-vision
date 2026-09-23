#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from uliana.config import load_config
from uliana.contracts.serialization import from_pose_frame
from uliana.contracts.validation import validate_contract
from uliana.pose_adapter import MediaPipeVideoPoseAdapter, sha256_file
from uliana.video.ingestion import VideoReader
from uliana.video.processing import process_observations,render_diagnostic_video,write_observations
from uliana.video_analysis import pose_frame_from_dict


def main()->int:
    parser=argparse.ArgumentParser(description="Create stable video observations and conservative camera diagnostics.")
    parser.add_argument("video",type=Path); parser.add_argument("--session-id",required=True)
    parser.add_argument("--output-dir",required=True,type=Path); parser.add_argument("--model",type=Path,default=ROOT/"models/pose_landmarker_full.task")
    parser.add_argument("--landmarks-jsonl",type=Path,help="Use an existing PoseFrame cache instead of running inference.")
    parser.add_argument("--config",type=Path,default=ROOT/"configs/video_processing.json")
    parser.add_argument("--json",nargs="?",const="-",dest="json_output"); parser.add_argument("--no-overlay",action="store_true")
    args=parser.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    config=load_config(args.config); fps_limits=config["plausible_fps"]
    metadata=VideoReader(args.video,fps_limits["minimum"],fps_limits["maximum"]).metadata()
    if args.landmarks_jsonl:
        frames=[pose_frame_from_dict(json.loads(line)) for line in args.landmarks_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        if not args.model.is_file(): print(f"ERROR: pose model not found: {args.model}",file=sys.stderr); return 1
        frames=[frame for frame,_ in MediaPipeVideoPoseAdapter(args.model).process(args.video)]
    raw=[from_pose_frame(frame,args.session_id,metadata.fps,metadata.width,metadata.height) for frame in frames]
    observations,summary=process_observations(raw,config)
    for observation in observations: validate_contract("video_observation",observation)
    output=args.output_dir/"video_observations.jsonl"; write_observations(output,observations)
    overlay=None
    if not args.no_overlay: overlay=args.output_dir/"video_diagnostic.mp4"; render_diagnostic_video(args.video,overlay,observations,summary)
    summary.update({"session_id":args.session_id,"video_metadata":metadata.__dict__,"video_observations_jsonl":str(output),
        "annotated_video":str(overlay) if overlay else None,"provenance":{"video_sha256":sha256_file(args.video),
        "model_sha256":sha256_file(args.model) if not args.landmarks_jsonl else None,"landmark_cache":str(args.landmarks_jsonl) if args.landmarks_jsonl else None,
        "python":platform.python_version(),"configuration":config,"world_landmark_caveat":"Monocular model coordinates are not ground-truth 3D motion capture."}})
    (args.output_dir/"video_summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    if args.json_output:
        payload=json.dumps(summary,indent=2,allow_nan=False)+"\n"
        if args.json_output=="-": print(payload,end="")
        else: Path(args.json_output).write_text(payload,encoding="utf-8")
    else:
        print(f"Video: {metadata.width}x{metadata.height} at {metadata.fps:.3f} FPS")
        print(f"Pose detection coverage: {summary['valid_pose_fraction']:.1%}")
        view=summary['dominant_viewpoint']; print(f"Dominant viewpoint: {view['value']} ({view['confidence']:.3f})")
        print(f"Observable anatomical side: {summary['observable_anatomical_side']}")
        print(f"Quality codes: {summary['quality_code_counts']}")
        print(f"Jitter raw/smoothed: {summary['jitter']}")
        print(f"Capabilities: {summary['capabilities']}")
        print(f"Video observations: {output}")
    return 0


if __name__=="__main__": raise SystemExit(main())
