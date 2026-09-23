from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

from .video_geometry import Landmark
from .video_timestamps import increasing_timestamp_ms

LANDMARK_NAMES = (
    "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right", "left_shoulder", "right_shoulder", "left_elbow",
    "right_elbow", "left_wrist", "right_wrist", "left_pinky", "right_pinky", "left_index", "right_index",
    "left_thumb", "right_thumb", "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle",
    "right_ankle", "left_heel", "right_heel", "left_foot_index", "right_foot_index",
)


@dataclass(frozen=True)
class PoseFrame:
    frame_index: int
    timestamp_ms: int
    timestamp_source: str
    detected: bool
    landmarks: dict[str, Landmark]
    inference_ms: float
    error: str | None = None
    world_landmarks: dict[str, Landmark] | None = None

    def to_dict(self) -> dict:
        value = asdict(self)
        value["landmarks"] = {name: asdict(point) for name, point in self.landmarks.items()}
        return value


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class MediaPipeVideoPoseAdapter:
    """Lazy-imported MediaPipe Tasks adapter; importing uliana does not require video extras."""

    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path)
        if not self.model_path.is_file():
            raise FileNotFoundError(f"pose model not found: {self.model_path}")

    def process(self, video_path: str | Path) -> Iterator[tuple[PoseFrame, object]]:
        try:
            import cv2
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError("video extras are required; use the documented Python 3.11 .venv-video setup") from exc
        import time

        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise ValueError(f"cannot open video: {video_path}")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
        )
        previous = None
        try:
            with mp.tasks.vision.PoseLandmarker.create_from_options(options) as landmarker:
                index = 0
                while True:
                    ok, bgr = capture.read()
                    if not ok:
                        break
                    raw_timestamp = capture.get(cv2.CAP_PROP_POS_MSEC)
                    timestamp, source = increasing_timestamp_ms(raw_timestamp, index, fps, previous)
                    previous = timestamp
                    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    started = time.perf_counter()
                    try:
                        result = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp)
                        elapsed = (time.perf_counter() - started) * 1000
                        points = {}
                        if result.pose_landmarks:
                            points = {name: Landmark(item.x, item.y, item.z, item.visibility or 0.0, item.presence or 0.0)
                                      for name, item in zip(LANDMARK_NAMES, result.pose_landmarks[0])}
                        world_points = None
                        if result.pose_world_landmarks:
                            world_points = {name: Landmark(item.x, item.y, item.z, item.visibility or 0.0, item.presence or 0.0)
                                            for name, item in zip(LANDMARK_NAMES, result.pose_world_landmarks[0])}
                        yield PoseFrame(index, timestamp, source, bool(points), points, elapsed, world_landmarks=world_points), bgr
                    except (RuntimeError, ValueError) as exc:
                        yield PoseFrame(index, timestamp, source, False, {}, (time.perf_counter() - started) * 1000,
                                        f"pose_inference_error:{type(exc).__name__}"), bgr
                    index += 1
        finally:
            capture.release()
