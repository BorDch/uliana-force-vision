from http.cookies import SimpleCookie

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from scripts import demo_server
from scripts.mobile_auth import MobileStore


def test_pairing_endpoint_upsert_revoke_and_rate_limit(tmp_path, monkeypatch):
    mobile = MobileStore(tmp_path / "auth.sqlite3", tmp_path / "data", "invite-code")
    monkeypatch.setattr(demo_server, "MOBILE", mobile)
    monkeypatch.setenv("ULIANA_RATE_LIMIT_PAIRING", "3")
    user = mobile.register("sensor_user", "correct-horse-1", "correct-horse-1", "invite-code")
    workout_id, _ = mobile.create_workout(user["id"])
    response = Response()
    mobile.issue_session(response, user["id"], secure=False)
    parsed = SimpleCookie()
    for header in response.headers.getlist("set-cookie"):
        parsed.load(header)
    cookie_header = "; ".join(f"{key}={morsel.value}" for key, morsel in parsed.items())
    request = Request({"type": "http", "method": "POST", "scheme": "http", "path": "/api/sensors/pairings",
                       "headers": [(b"cookie", cookie_header.encode()),
                                   (b"x-csrf-token", parsed["uliana_csrf"].value.encode())]})
    route = next(route for route in demo_server.app.routes if getattr(route, "path", None) == "/api/sensors/pairings" and "POST" in route.methods)
    assert route.status_code == 200
    first = demo_server.create_sensor_pairing(demo_server.PairingBody(device_id="esp32-demo-01"), request)
    mobile.store_sensor_sample(mobile.pairing_for_token(first["token"]), 1, 100, [], None)
    second = demo_server.create_sensor_pairing(demo_server.PairingBody(device_id="esp32-demo-01", workout_session_id=workout_id), request)
    assert second["pairing_id"] != first["pairing_id"]
    with mobile.connect() as db:
        rows = db.execute("SELECT * FROM sensor_pairings WHERE user_id=?", (user["id"],)).fetchall()
        assert len(rows) == 1 and rows[0]["id"] == second["pairing_id"]
        assert rows[0]["workout_id"] == workout_id
        assert db.execute("SELECT pairing_id FROM sensor_samples").fetchone()[0] == second["pairing_id"]
    with pytest.raises(HTTPException) as stale:
        demo_server.revoke_sensor_pairing(first["pairing_id"], request)
    assert stale.value.status_code == 404
    assert demo_server.revoke_sensor_pairing(second["pairing_id"], request) is None
    with mobile.connect() as db:
        assert db.execute("SELECT count(*) FROM sensor_pairings").fetchone()[0] == 0
    assert demo_server.create_sensor_pairing(demo_server.PairingBody(device_id="esp32-demo-01"), request)["pairing_id"]
    with pytest.raises(HTTPException) as limited:
        demo_server.create_sensor_pairing(demo_server.PairingBody(device_id="esp32-demo-01"), request)
    assert limited.value.status_code == 429
