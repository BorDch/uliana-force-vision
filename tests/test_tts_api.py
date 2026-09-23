import io
import wave
from http.cookies import SimpleCookie

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from scripts import demo_server
from scripts.mobile_auth import MobileStore


def request_for(store, user_id):
    response = Response()
    store.issue_session(response, user_id, secure=False)
    cookies = SimpleCookie()
    for header in response.headers.getlist("set-cookie"):
        cookies.load(header)
    csrf = cookies["uliana_csrf"].value
    cookie = "; ".join(f"{key}={morsel.value}" for key, morsel in cookies.items())
    return Request({"type": "http", "method": "POST", "path": "/api/tts/synthesize",
                    "headers": [(b"cookie", cookie.encode()), (b"x-csrf-token", csrf.encode())]})


def fake_wav(*_):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(24000)
        file.writeframes(b"\0\0")
    return stream.getvalue()


def test_tts_endpoint_auth_validation_and_ownership(tmp_path, monkeypatch):
    mobile = MobileStore(tmp_path / "auth.sqlite3", tmp_path / "data", "invite-code")
    alice = mobile.register("tts_alice", "correct-horse-1", "correct-horse-1", "invite-code")
    bob = mobile.register("tts_bob", "correct-horse-2", "correct-horse-2", "invite-code")
    workout_id, _ = mobile.create_workout(alice["id"])
    monkeypatch.setattr(demo_server, "MOBILE", mobile)
    monkeypatch.setattr(demo_server, "synthesize_wav", fake_wav)
    assert any(route.path == "/api/tts/synthesize" for route in demo_server.app.routes)
    alice_request = request_for(mobile, alice["id"])
    bob_request = request_for(mobile, bob["id"])
    invoke = demo_server.tts_synthesize
    response = invoke(demo_server.TTSBody(text="Keep your hips in line.", session_id=workout_id), alice_request)
    assert response.media_type == "audio/wav" and response.body.startswith(b"RIFF")
    for text in ("", "x" * 501):
        with pytest.raises(HTTPException) as error:
            invoke(demo_server.TTSBody(text=text), alice_request)
        assert error.value.status_code == 400
    anonymous = Request({"type": "http", "method": "POST", "path": "/api/tts/synthesize", "headers": []})
    with pytest.raises(HTTPException) as error:
        invoke(demo_server.TTSBody(text="Keep your hips in line."), anonymous)
    assert error.value.status_code == 401
    with pytest.raises(HTTPException) as error:
        invoke(demo_server.TTSBody(text="Keep your hips in line.", session_id=workout_id), bob_request)
    assert error.value.status_code == 404
