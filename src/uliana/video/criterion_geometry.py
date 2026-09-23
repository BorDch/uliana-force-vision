from __future__ import annotations

import math


def _usable(frame, names, config):
    limits = config["landmark_quality"]
    return frame.pose.detected and all(
        name in frame.pose.landmarks
        and (frame.pose.landmarks[name].visibility or 0) >= limits["minimum_visibility"]
        and (frame.pose.landmarks[name].presence or 0) >= limits["minimum_presence"]
        and math.isfinite(frame.pose.landmarks[name].x)
        and math.isfinite(frame.pose.landmarks[name].y)
        for name in names)


def _extract_head_neck_data(frames, observable_side, config):
    """Signed ear distance from the shoulder-hip line / pixel torso length.

    Side/oblique 2D proxy only: frontal head centering is not neck alignment.
    """
    if observable_side not in ("left", "right"):
        return None
    names = [f"{observable_side}_{part}" for part in ("ear", "shoulder", "hip")]
    results = []
    for frame in frames:
        if not _usable(frame, names, config):
            continue
        ear, shoulder, hip = [frame.pose.landmarks[name] for name in names]
        w, h = frame.image_width_px, frame.image_height_px
        vx, vy = (hip.x-shoulder.x)*w, (hip.y-shoulder.y)*h
        length2 = vx*vx + vy*vy
        if length2 <= 1:
            continue
        ex, ey = (ear.x-shoulder.x)*w, (ear.y-shoulder.y)*h
        results.append((frame.timestamp_ms, (vx*ey-vy*ex)/length2, ear.y))
    return results or None
