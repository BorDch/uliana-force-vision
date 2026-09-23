#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jsonschema import validate

from uliana.config import load_config
from uliana.pose_adapter import LANDMARK_NAMES, MediaPipeVideoPoseAdapter, PoseFrame, sha256_file
from uliana.session import write_jsonl as write_replay_jsonl
from uliana.video_analysis import analyze_pose_frames, pose_frame_from_dict, replay_packets, write_jsonl

CONNECTIONS = ((11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24), (23, 27), (24, 28))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze one recorded side-view push-up video offline.")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "real_video.json")
    parser.add_argument("--simulated-force", action="store_true", help="Emit schema replay with clearly labelled simulated, not measured, force.")
    parser.add_argument("--no-cache", action="store_true", help="Rerun inference even when landmarks.jsonl exists.")
    return parser.parse_args()


def video_info(video: Path) -> dict:
    import cv2
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened(): raise ValueError(f"cannot open video: {video}")
    info = {"width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "reported_fps": float(capture.get(cv2.CAP_PROP_FPS)), "reported_frame_count": int(capture.get(cv2.CAP_PROP_FRAME_COUNT))}
    capture.release()
    info["reported_duration_seconds"] = info["reported_frame_count"] / info["reported_fps"] if info["reported_fps"] > 0 else None
    return info


def load_or_infer(args: argparse.Namespace) -> list[PoseFrame]:
    cache = args.output / "landmarks.jsonl"
    if cache.exists() and not args.no_cache:
        return [pose_frame_from_dict(json.loads(line)) for line in cache.read_text(encoding="utf-8").splitlines() if line.strip()]
    frames = []
    adapter = MediaPipeVideoPoseAdapter(args.model)
    for pose_frame, _ in adapter.process(args.video): frames.append(pose_frame)
    write_jsonl(cache, [frame.to_dict() for frame in frames])
    return frames


def render_overlay(video: Path, destination: Path, diagnostics: list[dict], frames: list[PoseFrame], info: dict) -> None:
    import cv2
    capture = cv2.VideoCapture(str(video))
    fps = info["reported_fps"] if info["reported_fps"] > 0 else 30.0
    writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"mp4v"), fps, (info["width"], info["height"]))
    if not writer.isOpened(): raise RuntimeError(f"cannot create overlay: {destination}")
    try:
        index = 0
        while True:
            ok, image = capture.read()
            if not ok: break
            if index >= len(diagnostics): break
            diagnostic, pose = diagnostics[index], frames[index]
            for a, b in CONNECTIONS:
                if a < len(LANDMARK_NAMES) and b < len(LANDMARK_NAMES):
                    pa, pb = pose.landmarks.get(LANDMARK_NAMES[a]), pose.landmarks.get(LANDMARK_NAMES[b])
                    if pa and pb:
                        cv2.line(image, (round(pa.x * info["width"]), round(pa.y * info["height"])),
                                 (round(pb.x * info["width"]), round(pb.y * info["height"])), (80, 220, 160), 2)
            status = "assessment available" if diagnostic["assessment_available"] else f"unavailable: {diagnostic['reliability_reason']}"
            cv2.putText(image, f"Rep {diagnostic['rep_count']} | {status}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, .7,
                        (70, 220, 150) if diagnostic["assessment_available"] else (80, 80, 255), 2)
            cv2.putText(image, "CAMERA-ONLY | FORCE UNAVAILABLE", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, .6, (50, 190, 255), 2)
            writer.write(image); index += 1
    finally:
        capture.release(); writer.release()


def main() -> None:
    args = parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    if not args.video.is_file(): raise SystemExit(f"video not found: {args.video}")
    if not args.model.is_file(): raise SystemExit(f"model not found: {args.model}")
    config = load_config(args.config)
    info = video_info(args.video)
    frames = load_or_infer(args)
    if not frames: raise SystemExit("video yielded no decodable frames")
    diagnostics, repetitions, side, side_reason = analyze_pose_frames(frames, info["width"], info["height"], config)
    write_jsonl(args.output / "frames.jsonl", diagnostics)
    (args.output / "repetitions.json").write_text(json.dumps([asdict(rep) for rep in repetitions], indent=2, allow_nan=False) + "\n", encoding="utf-8")
    render_overlay(args.video, args.output / "annotated.mp4", diagnostics, frames, info)
    timestamp_sources = Counter(frame.timestamp_source for frame in frames)
    inference = [frame.inference_ms for frame in frames]
    provenance = {"mode": "real_video_camera_only", "force_provenance": "simulated_for_dashboard_only" if args.simulated_force else "unavailable",
        "video": str(args.video), "video_sha256": sha256_file(args.video), "model": str(args.model), "model_sha256": sha256_file(args.model),
        "model_source": "https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python",
        "runtime": {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
                    "processor": platform.processor() or "unreported"},
        "config": config, "video_info": info, "selected_anatomical_side": side,
        "side_selection_reason": side_reason, "timestamp_sources": timestamp_sources,
        "overlay_timing": "constant-frame-rate at decoder-reported average FPS; source duration retained approximately; VFR timestamps remain exact in JSONL",
        "world_coordinate_caveat": "MediaPipe monocular world coordinates are model estimates and are not used as motion-capture truth",
        "visibility_caveat": "Visibility/presence are quality signals, not calibrated probabilities of correct advice"}
    (args.output / "provenance.json").write_text(json.dumps(provenance, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    schema_replay = None
    if args.simulated_force:
        packets = replay_packets(repetitions, args.video.stem, config)
        schema = json.loads((ROOT / "schemas" / "analysis-result.schema.json").read_text(encoding="utf-8"))
        for packet in packets: validate(packet.to_dict(), schema)
        schema_replay = "replay.jsonl"; write_replay_jsonl(args.output / schema_replay, packets)
    summary = {"video_id": args.video.stem, "frames": len(frames), "detected_repetitions": len(repetitions),
        "selected_anatomical_side": side, "required_landmark_availability": sum(x["assessment_available"] for x in diagnostics) / len(diagnostics),
        "decision_coverage": (sum(not repetition.abstained for repetition in repetitions) / len(repetitions)) if repetitions else None,
        "mean_inference_ms_per_frame_excluding_warmup": (sum(inference[5:]) / len(inference[5:])) if len(inference) > 5 else None,
        "replay_output": schema_replay, "replay_limitation": "Existing schema requires numeric force and balance fields; camera-only mode does not fabricate them. Use --simulated-force only for UI integration."}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__": main()
