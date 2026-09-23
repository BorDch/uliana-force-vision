from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Any

from .timestamps import increasing_timestamp_ms


@dataclass(frozen=True)
class VideoMetadata:
    path: str
    fps: float
    width: int
    height: int
    reported_frame_count: int
    reported_duration_seconds: float | None
    one_person_assumption: bool
    warnings: list[str]


@dataclass(frozen=True)
class DecodedVideoFrame:
    frame_index: int
    timestamp_ms: int
    timestamp_source: str
    fps: float
    width: int
    height: int
    image: Any


class VideoReader:
    """OpenCV reader whose timestamps are always source-relative, never wall-clock time."""

    def __init__(self, path: str | Path, minimum_fps: float = 5, maximum_fps: float = 240):
        self.path = Path(path); self.minimum_fps = minimum_fps; self.maximum_fps = maximum_fps

    def _open(self):
        try: import cv2
        except ImportError as exc: raise RuntimeError("video extras are required") from exc
        capture = cv2.VideoCapture(str(self.path))
        if not capture.isOpened(): raise ValueError(f"cannot open video: {self.path}")
        return capture, cv2

    def metadata(self) -> VideoMetadata:
        capture, cv2 = self._open()
        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS)); width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)); height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)); warnings = ["one_person_assumption"]
            if width <= 0 or height <= 0: raise ValueError("video dimensions must be positive")
            if not self.minimum_fps <= fps <= self.maximum_fps: warnings.append("implausible_reported_fps")
            if fps <= 0: raise ValueError("video has no positive FPS fallback")
            return VideoMetadata(str(self.path), fps, width, height, count, count/fps if count >= 0 else None, True, warnings)
        finally: capture.release()

    def frames(self) -> Iterator[DecodedVideoFrame]:
        capture, cv2 = self._open(); meta = self.metadata(); previous = None; index = 0
        try:
            while True:
                ok, image = capture.read()
                if not ok: break
                raw = capture.get(cv2.CAP_PROP_POS_MSEC)
                timestamp, source = increasing_timestamp_ms(raw, index, meta.fps, previous)
                if source != "container_timestamp" and "fallback" not in source:
                    source = f"{source}_explicit"
                previous = timestamp
                yield DecodedVideoFrame(index, timestamp, source, meta.fps, meta.width, meta.height, image)
                index += 1
        finally: capture.release()
