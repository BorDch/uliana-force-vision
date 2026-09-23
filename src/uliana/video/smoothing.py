from __future__ import annotations

import math
from dataclasses import replace

from uliana.contracts.models import LandmarkObservation, PoseObservation, VideoObservation


class _OneEuroCoordinate:
    def __init__(self, min_cutoff: float, beta: float, derivative_cutoff: float):
        self.min_cutoff=min_cutoff; self.beta=beta; self.derivative_cutoff=derivative_cutoff
        self.value=None; self.derivative=0.0; self.timestamp=None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1/(2*math.pi*cutoff); return 1/(1+tau/dt)

    def update(self, value: float, timestamp_ms: int) -> float:
        if self.value is None or self.timestamp is None:
            self.value=value; self.timestamp=timestamp_ms; return value
        dt=(timestamp_ms-self.timestamp)/1000
        if dt <= 0: return self.value
        derivative=(value-self.value)/dt
        da=self._alpha(self.derivative_cutoff,dt); self.derivative=da*derivative+(1-da)*self.derivative
        alpha=self._alpha(self.min_cutoff+self.beta*abs(self.derivative),dt)
        self.value=alpha*value+(1-alpha)*self.value; self.timestamp=timestamp_ms; return self.value


class LandmarkSmoother:
    """Causal timestamp-driven One Euro filters, independent for every landmark x/y/z coordinate."""
    def __init__(self, config: dict):
        self.parameters=config["smoothing"]; self.maximum_gap_ms=config["maximum_pose_gap_ms"]
        self.filters={}; self.last_timestamp=None

    def reset(self): self.filters={}; self.last_timestamp=None

    def process(self, observation: VideoObservation) -> VideoObservation:
        gap = self.last_timestamp is not None and observation.timestamp_ms-self.last_timestamp > self.maximum_gap_ms
        if gap: self.reset()
        raw=observation.pose.landmarks
        if not observation.pose.detected:
            if self.last_timestamp is not None and observation.timestamp_ms-self.last_timestamp > self.maximum_gap_ms: self.reset()
            flags=list(dict.fromkeys(observation.quality_flags+["pose_not_detected"])); return replace(observation,quality_flags=flags)
        output={}
        for name, point in raw.items():
            valid=all(math.isfinite(value) for value in (point.x,point.y))
            if not valid: continue
            coordinates=[]
            for coordinate,value in (("x",point.x),("y",point.y),("z",point.z)):
                if value is None or not math.isfinite(value): coordinates.append(value); continue
                key=(name,coordinate)
                if key not in self.filters: self.filters[key]=_OneEuroCoordinate(**self.parameters)
                coordinates.append(self.filters[key].update(value,observation.timestamp_ms))
            output[name]=LandmarkObservation(*coordinates,point.visibility,point.presence)
        self.last_timestamp=observation.timestamp_ms
        pose=PoseObservation(observation.pose.detected,output,observation.pose.model_confidence,
                             observation.pose.raw_landmarks or raw,observation.pose.world_landmarks,
                             observation.pose.world_landmarks_caveat)
        flags=list(observation.quality_flags)
        if gap: flags.append("excessive_pose_gap")
        return replace(observation,pose=pose,quality_flags=list(dict.fromkeys(flags)))
