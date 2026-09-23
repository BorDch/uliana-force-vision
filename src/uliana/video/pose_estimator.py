from __future__ import annotations

from pathlib import Path
from typing import Iterator

from uliana.contracts.models import LandmarkObservation, PoseObservation, VideoObservation, ViewpointEstimate
from uliana.pose_adapter import MediaPipeVideoPoseAdapter


class MediaPipeObservationAdapter:
    """Stable-contract wrapper around the sole existing MediaPipe initialization path."""

    def __init__(self, model_path: str | Path): self.adapter = MediaPipeVideoPoseAdapter(model_path)

    def process(self, video_path: str | Path, session_id: str) -> Iterator[tuple[VideoObservation, object]]:
        try: import cv2
        except ImportError as exc: raise RuntimeError("video extras are required") from exc
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened(): raise ValueError(f"cannot open video: {video_path}")
        fps = float(capture.get(cv2.CAP_PROP_FPS)); width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)); height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)); capture.release()
        if fps <= 0 or width <= 0 or height <= 0: raise ValueError("video FPS and dimensions must be positive")
        for frame, image in self.adapter.process(video_path):
            landmarks = {name: LandmarkObservation(p.x, p.y, p.z, p.visibility, p.presence) for name, p in frame.landmarks.items()}
            world = {name: LandmarkObservation(p.x, p.y, p.z, p.visibility, p.presence)
                     for name, p in (frame.world_landmarks or {}).items()} or None
            flags = ([frame.error] if frame.error else []) + ([] if frame.detected else ["pose_not_detected"])
            yield VideoObservation("1.0", session_id, frame.frame_index, frame.timestamp_ms, frame.timestamp_source,
                fps, width, height, PoseObservation(frame.detected, landmarks, None, landmarks.copy(), world,
                "MediaPipe monocular world coordinates are model estimates, not ground-truth motion capture." if world else None),
                ViewpointEstimate("unknown", None, "not_yet_aggregated"), flags), image
