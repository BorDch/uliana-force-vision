from pathlib import Path

import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request

from scripts import demo_server


def request() -> Request:
    return Request({"type": "http", "method": "POST", "scheme": "http", "path": "/api/sessions", "headers": []})


def test_exercise_type_is_saved_and_unassessed_variant_skips_standard_analysis(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(demo_server, "MOBILE", None)
    monkeypatch.setattr(demo_server, "STORE", tmp_path)
    created = demo_server.create_session(demo_server.NewSession(exercise="push-up", consent=True, exercise_type="diamond"), request())
    assert created["exercise_type"] == "diamond"
    target = tmp_path / created["session_id"]
    assert demo_server.read_meta(target)["exercise_type"] == "diamond"
    (target / "source.mp4").write_bytes(b"saved video")
    tasks = BackgroundTasks()
    result = demo_server.analyse(created["session_id"], tasks, request())
    assert result["assessment"] == "not_assessed_in_this_version"
    assert demo_server.read_meta(target)["status"] == "completed"
    assert not tasks.tasks
    assert demo_server.public_result(target)["exercise_type"] == "diamond"
    assert "assessments" not in demo_server.public_result(target)


def test_unknown_exercise_type_is_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(demo_server, "MOBILE", None)
    monkeypatch.setattr(demo_server, "STORE", tmp_path)
    with pytest.raises(HTTPException) as error:
        demo_server.create_session(demo_server.NewSession(exercise="push-up", consent=True, exercise_type="unlisted"), request())
    assert error.value.status_code == 400
