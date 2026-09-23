"""Read-only review moments from saved observations and frozen camera features."""
from __future__ import annotations

import json
import math
from pathlib import Path


def _geometry(landmarks: dict, side: str, width: int, height: int, visibility: float, presence: float):
    names = tuple(f"{side}_{joint}" for joint in ("shoulder", "hip", "ankle"))
    points = [landmarks.get(name) for name in names]
    if any(not point or point.get("visibility", 0) < visibility or point.get("presence", 0) < presence for point in points):
        return None
    if any(not 0 <= point.get(axis, -1) <= 1 for point in points for axis in ("x", "y")):
        return None
    shoulder, hip, ankle = points
    ax, ay = shoulder["x"] * width, shoulder["y"] * height
    bx, by = ankle["x"] * width, ankle["y"] * height
    px, py = hip["x"] * width, hip["y"] * height
    vx, vy = bx - ax, by - ay
    length = math.hypot(vx, vy)
    if length <= 1:
        return None
    signed = (vx * (py - ay) - vy * (px - ax)) / (length * length)
    projection = ((px - ax) * vx + (py - ay) * vy) / (length * length)
    target = {"x": (ax + projection * vx) / width, "y": (ay + projection * vy) / height}
    return names, points, target, signed


def review_moments(folder: Path) -> dict:
    analysis = folder / "analysis"
    required = ("session_result.json", "video_summary.json", "camera_repetition_features.json", "video_observations.jsonl")
    if any(not (analysis / name).is_file() for name in required):
        return {"moments": []}
    result = json.loads((analysis / required[0]).read_text(encoding="utf-8"))
    summary = json.loads((analysis / required[1]).read_text(encoding="utf-8"))
    features = json.loads((analysis / required[2]).read_text(encoding="utf-8"))
    side = summary.get("observable_anatomical_side")
    if side not in ("left", "right"):
        return {"moments": []}
    quality = result.get("provenance", {}).get("experimental_configuration", {}).get("landmark_quality", {})
    visibility, presence = quality.get("minimum_visibility"), quality.get("minimum_presence")
    if not isinstance(visibility, (int, float)) or not isinstance(presence, (int, float)):
        return {"moments": []}
    flags = {item["rep_id"]: item for item in result.get("assessments", [])
             if item.get("condition") == "body_alignment_deviation"
             and item.get("result") == "condition_detected" and item.get("rep_id") is not None}
    candidates = {}
    for feature in features:
        rep_id = feature.get("rep_id")
        if rep_id not in flags:
            continue
        evidence = flags[rep_id].get("evidence", {})
        limits = evidence.get("experimental_thresholds", {})
        distance_limit, angle_limit = limits.get("normalized_hip_displacement"), limits.get("angle_deviation_deg")
        if not all(isinstance(value, (int, float)) and value > 0 for value in (distance_limit, angle_limit)):
            continue
        angles = dict(feature.get("alignment_angle_deviation_deg") or [])
        rows = []
        for stamp, distance in feature.get("normalized_hip_displacement") or []:
            angle = angles.get(stamp, 0)
            if abs(distance) > distance_limit or angle > angle_limit:
                rows.append((max(abs(distance) / distance_limit, angle / angle_limit), stamp, abs(distance), angle))
        if rows:
            candidates[rep_id] = (sorted(rows, reverse=True), evidence)
    if not candidates:
        return {"moments": []}
    wanted = {stamp for rows, _ in candidates.values() for _, stamp, _, _ in rows}
    frames = {}
    with (analysis / required[3]).open(encoding="utf-8") as stream:
        for line in stream:
            frame = json.loads(line)
            if frame.get("timestamp_ms") in wanted:
                frames[frame["timestamp_ms"]] = frame
    moments = []
    for rep_id, (rows, evidence) in sorted(candidates.items()):
        for _, stamp, frozen_distance, frozen_angle in rows:
            frame = frames.get(stamp)
            if not frame or not frame.get("pose", {}).get("detected"):
                continue
            width, height = frame.get("image_width_px"), frame.get("image_height_px")
            if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
                continue
            geometry = _geometry(frame["pose"].get("landmarks", {}), side, width, height, visibility, presence)
            if geometry is None:
                continue
            names, points, target, signed = geometry
            if not math.isclose(abs(signed), frozen_distance, rel_tol=1e-3, abs_tol=1e-4):
                continue
            shoulder, hip, ankle = points
            moments.append({"rep_id": rep_id, "timestamp_ms": stamp, "landmark_names": names,
                            "shoulder": {"x": shoulder["x"], "y": shoulder["y"]},
                            "hip": {"x": hip["x"], "y": hip["y"]},
                            "ankle": {"x": ankle["x"], "y": ankle["y"]},
                            "target": target, "signed_deviation": signed,
                            "normalized_hip_displacement": frozen_distance,
                            "alignment_angle_deviation_deg": frozen_angle,
                            "frozen_maximum_normalized_hip_displacement": evidence.get("maximum_normalized_hip_displacement"),
                            "image_width_px": width, "image_height_px": height})
            break
    return {"moments": moments}
