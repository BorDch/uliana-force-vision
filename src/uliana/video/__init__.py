"""Reusable real-video diagnostics built around the stable VideoObservation contract."""

from .ingestion import DecodedVideoFrame, VideoMetadata, VideoReader
from .landmark_quality import FrameQuality, assess_landmark_quality
from .pose_estimator import MediaPipeObservationAdapter
from .smoothing import LandmarkSmoother
from .viewpoint import ViewpointFrameEvidence, ViewpointTracker, classify_viewpoint, summarize_viewpoints

__all__ = ["DecodedVideoFrame", "FrameQuality", "LandmarkSmoother", "MediaPipeObservationAdapter",
           "VideoMetadata", "VideoReader", "ViewpointFrameEvidence", "ViewpointTracker",
           "assess_landmark_quality", "classify_viewpoint", "summarize_viewpoints"]
