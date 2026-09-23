import json
from http.cookies import SimpleCookie

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from scripts import demo_server
from scripts.hand_width import classify_hand_width
from scripts.mobile_auth import MobileStore


def request_with(cookies, csrf=False):
    cookie = "; ".join(f"{key}={value}" for key, value in cookies.items())
    headers = [(b"cookie", cookie.encode())]
    if csrf:
        headers.append((b"x-csrf-token", cookies["uliana_csrf"].encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def authenticated_client(tmp_path, monkeypatch):
    mobile = MobileStore(tmp_path / "auth.sqlite3", tmp_path / "data", "invite-code")
    monkeypatch.setattr(demo_server, "MOBILE", mobile)
    user = mobile.register("hand_width_user", "correct-horse-1", "correct-horse-1", "invite-code")
    response = Response()
    mobile.issue_session(response, user["id"], secure=False)
    cookies = SimpleCookie()
    for header in response.headers.getlist("set-cookie"):
        cookies.load(header)
    values = {key: morsel.value for key, morsel in cookies.items()}
    return mobile, user, request_with(values), request_with(values, csrf=True)


def write_camera(path, shoulder_left=.3, shoulder_right=.7, wrist_left=.25, wrist_right=.75):
    analysis = path / "analysis"
    analysis.mkdir()
    landmarks = {
        "left_shoulder": point(shoulder_left), "right_shoulder": point(shoulder_right),
        "left_wrist": point(wrist_left), "right_wrist": point(wrist_right),
    }
    frame = {"timestamp_ms": 100, "pose": {"detected": True, "landmarks": landmarks}}
    (analysis / "video_observations.jsonl").write_text(json.dumps(frame) + "\n", encoding="utf-8")


def point(x):
    return {"x": x, "y": .5, "visibility": 1, "presence": 1}


def test_shoulder_calibration_valid_and_missing(tmp_path, monkeypatch):
    mobile, user, _, csrf_request = authenticated_client(tmp_path, monkeypatch)
    valid = demo_server.calibrate_shoulders(demo_server.ShoulderCalibrationBody(shoulder_width_norm=.42), csrf_request)
    assert valid == {"shoulder_width_cm": 42.0, "saved": True}
    assert mobile.shoulder_calibration(user["id"]) == {"shoulder_width_norm": .42, "shoulder_width_cm": 42.0}
    with pytest.raises(HTTPException) as missing:
        demo_server.calibrate_shoulders(demo_server.ShoulderCalibrationBody(), csrf_request)
    assert missing.value.status_code == 400


def test_hand_width_returns_deviation_and_sensor_agreement(tmp_path, monkeypatch):
    mobile, _, request, csrf_request = authenticated_client(tmp_path, monkeypatch)
    assert demo_server.calibrate_shoulders(demo_server.ShoulderCalibrationBody(shoulder_width_norm=.4), csrf_request)["saved"]
    session_id, path = mobile.create_workout(mobile.authenticate("hand_width_user", "correct-horse-1")["id"])
    write_camera(path)
    pairing = mobile.create_pairing(
        mobile.authenticate("hand_width_user", "correct-horse-1")["id"],
        "esp32-demo-01",
        workout_id=session_id,
    )
    baseline = {f"channel_{channel}": 1000 for channel in range(16)}
    channels = [
        {"channel_id": f"channel_{channel}", "raw_value": 900 if channel in {13, 1} else 1000}
        for channel in range(16)
    ]
    mobile.store_sensor_sample(mobile.pairing_for_token(pairing["token"]), 1, 100, channels, session_id, baseline)
    payload = demo_server.hand_width_for_session(session_id, request)
    assert payload["shoulder_width_cm"] == 40
    assert payload["hand_width_cm"] == 50
    assert payload["deviation_cm"] == 10
    assert payload["classification"] == "too wide"
    assert payload["sensor_hand_width_cm"] == 50
    assert payload["sensor_camera_agree"] is True
    assert payload["calibration_used"] is True


def test_hand_width_without_sensor_returns_null(tmp_path, monkeypatch):
    mobile, user, request, _ = authenticated_client(tmp_path, monkeypatch)
    session_id, path = mobile.create_workout(user["id"])
    write_camera(path)
    payload = demo_server.hand_width_for_session(session_id, request)
    assert payload["hand_width_cm"] == 50
    assert payload["sensor_hand_width_cm"] is None
    assert payload["sensor_camera_agree"] is None


def test_hand_width_without_camera_returns_200_with_null(tmp_path, monkeypatch):
    mobile, user, request, _ = authenticated_client(tmp_path, monkeypatch)
    session_id, _ = mobile.create_workout(user["id"])
    payload = demo_server.hand_width_for_session(session_id, request)
    assert payload["hand_width_cm"] is None
    assert payload["classification"] is None


@pytest.mark.parametrize(
    "deviation,expected",
    [(0, "aligned"), (2.9, "aligned"), (3, "slightly wide"), (-7.9, "slightly narrow"),
     (8, "too wide"), (-8, "too narrow")],
)
def test_hand_width_classification_boundaries(deviation, expected):
    assert classify_hand_width(deviation)[0] == expected
