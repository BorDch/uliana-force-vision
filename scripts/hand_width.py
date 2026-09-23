"""Interpretable hand-width comparison for the mobile push-up prototype."""
from __future__ import annotations

import json
from pathlib import Path


SENSOR_X = {
    13: .25, 15: .12, 9: .38, 14: .12, 8: .38, 10: .12, 12: .38, 11: .25,
    1: .75, 4: .62, 0: .88, 7: .62, 2: .88, 6: .62, 3: .88, 5: .75,
}


def classify_hand_width(deviation_cm: float) -> tuple[str, str]:
    magnitude = abs(deviation_cm)
    direction = "wide" if deviation_cm > 0 else "narrow"
    if magnitude < 3:
        return "aligned", "Keep your hands aligned with shoulder width."
    if magnitude < 8:
        return f"slightly {direction}", (
            "Bring hands slightly closer." if deviation_cm > 0 else "Widen hands slightly."
        )
    return f"too {direction}", (
        "Bring hands closer to shoulder width." if deviation_cm > 0 else "Widen hands to shoulder width."
    )


def camera_measurement(path: Path, preferred_timestamp_ms: int | None = None) -> dict | None:
    if not path.is_file():
        return None
    candidates = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            frame = json.loads(line)
            if not frame.get("pose", {}).get("detected"):
                continue
            landmarks = frame["pose"].get("landmarks", {})
            names = ("left_shoulder", "right_shoulder", "left_wrist", "right_wrist")
            if any(not _valid_landmark(landmarks.get(name)) for name in names):
                continue
            candidates.append(frame)
    if not candidates:
        return None
    selected = min(
        candidates,
        key=lambda frame: abs(frame.get("timestamp_ms", 0) - preferred_timestamp_ms),
    ) if preferred_timestamp_ms is not None else candidates[0]
    landmarks = selected["pose"]["landmarks"]
    left_shoulder = landmarks["left_shoulder"]["x"]
    right_shoulder = landmarks["right_shoulder"]["x"]
    left_wrist = landmarks["left_wrist"]["x"]
    right_wrist = landmarks["right_wrist"]["x"]
    shoulder_width_norm = abs(right_shoulder - left_shoulder)
    if shoulder_width_norm <= 0:
        return None
    return {
        "timestamp_ms": selected.get("timestamp_ms"),
        "shoulder_width_norm": shoulder_width_norm,
        "hand_width_norm": abs(right_wrist - left_wrist),
        "expected_shoulders": {"left_x": left_shoulder, "right_x": right_shoulder},
    }


def sensor_hand_width_cm(device: dict | None) -> float | None:
    if not device:
        return None
    active = []
    for channel in device.get("channels", []):
        if channel.get("hand") is not True:
            continue
        try:
            number = int(str(channel["channel_id"]).removeprefix("channel_"))
        except (KeyError, ValueError):
            continue
        if number in SENSOR_X:
            active.append((number, SENSOR_X[number]))
    left = [x for channel, x in active if channel >= 8]
    right = [x for channel, x in active if channel < 8]
    if not left or not right:
        return None
    # The prototype mat coordinate system is normalized to a nominal 100 cm width.
    return round(abs(sum(right) / len(right) - sum(left) / len(left)) * 100, 1)


def _valid_landmark(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    x = value.get("x")
    return isinstance(x, (int, float)) and 0 <= x <= 1 and value.get("visibility", 1) >= .5 and value.get("presence", 1) >= .5
