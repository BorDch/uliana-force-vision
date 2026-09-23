from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from scripts.mobile_auth import MobileStore
from scripts.mobile_auth import request_is_secure
from starlette.requests import Request
from starlette.responses import Response


def store(tmp_path: Path) -> MobileStore:
    return MobileStore(tmp_path / "auth.sqlite3", tmp_path / "runtime", "invite-code")


def test_registration_is_case_insensitive_and_password_uses_scrypt(tmp_path):
    mobile = store(tmp_path)
    user = mobile.register("Alice", "correct-horse-1", "correct-horse-1", "invite-code")
    assert mobile.authenticate("alice", "correct-horse-1")["id"] == user["id"]
    with mobile.connect() as db:
        encoded = db.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()[0]
    assert encoded.startswith("scrypt$") and "correct-horse-1" not in encoded
    with pytest.raises(HTTPException) as conflict:
        mobile.register("ALICE", "another-password", "another-password", "invite-code")
    assert conflict.value.status_code == 409


def test_workout_ownership_persists_after_store_restart_and_legacy_is_hidden(tmp_path):
    mobile = store(tmp_path)
    alice = mobile.register("alice", "correct-horse-1", "correct-horse-1", "invite-code")
    bob = mobile.register("bob_user", "correct-horse-2", "correct-horse-2", "invite-code")
    workout_id, path = mobile.create_workout(alice["id"])
    (path / "metadata.json").write_text('{"status":"completed"}\n', encoding="utf-8")
    mobile.set_status(workout_id, "completed")
    legacy = mobile.data_dir / "legacy-session-without-owner"
    legacy.mkdir(); (legacy / "metadata.json").write_text("{}", encoding="utf-8")

    restarted = MobileStore(mobile.db_path, mobile.data_dir, "invite-code")
    assert [row["id"] for row in restarted.list_workouts(alice["id"])] == [workout_id]
    assert restarted.list_workouts(bob["id"]) == []
    with pytest.raises(HTTPException) as forbidden_lookup:
        restarted.workout(workout_id, bob["id"])
    assert forbidden_lookup.value.status_code == 404


def test_job_ownership_and_account_deletion_remove_files(tmp_path):
    mobile = store(tmp_path)
    alice = mobile.register("alice", "correct-horse-1", "correct-horse-1", "invite-code")
    bob = mobile.register("bob_user", "correct-horse-2", "correct-horse-2", "invite-code")
    workout_id, path = mobile.create_workout(alice["id"])
    (path / "source.mp4").write_bytes(b"private video")
    job_id = mobile.create_job(workout_id, alice["id"])
    with pytest.raises(HTTPException) as foreign_job:
        mobile.job(job_id, bob["id"])
    assert foreign_job.value.status_code == 404
    mobile.delete_account(alice["id"])
    assert not path.exists()
    with mobile.connect() as db:
        assert db.execute("SELECT count(*) FROM workout_sessions WHERE user_id=?", (alice["id"],)).fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM processing_jobs WHERE user_id=?", (alice["id"],)).fetchone()[0] == 0


def test_forwarded_https_is_trusted_only_when_explicitly_enabled(monkeypatch):
    request = Request({"type":"http","method":"GET","scheme":"http","path":"/","headers":[(b"x-forwarded-proto",b"https")],"server":("localhost",80)})
    monkeypatch.delenv("ULIANA_TRUST_PROXY", raising=False)
    assert not request_is_secure(request)
    monkeypatch.setenv("ULIANA_TRUST_PROXY", "1")
    assert request_is_secure(request)


def test_session_cookie_is_http_only_lax_and_secure_for_https(tmp_path):
    mobile = store(tmp_path)
    user = mobile.register("cookie_user", "correct-horse-4", "correct-horse-4", "invite-code")
    response = Response()
    mobile.issue_session(response, user["id"], secure=True)
    cookies = "\n".join(response.headers.getlist("set-cookie")).lower()
    assert "uliana_session=" in cookies and "httponly" in cookies
    assert "secure" in cookies and "samesite=lax" in cookies


def test_sensor_pairing_is_owned_revocable_and_persistent(tmp_path):
    mobile = store(tmp_path)
    alice = mobile.register("sensor_alice", "correct-horse-1", "correct-horse-1", "invite-code")
    bob = mobile.register("sensor_bob", "correct-horse-2", "correct-horse-2", "invite-code")
    workout_id, _ = mobile.create_workout(alice["id"])
    pairing = mobile.create_pairing(alice["id"], "esp32-demo-01")
    assert mobile.sensor_status(bob["id"]) == []
    with pytest.raises(HTTPException):
        mobile.revoke_pairing(pairing["pairing_id"], bob["id"])
    token_row = mobile.pairing_for_token(pairing["token"])
    first = mobile.store_sensor_sample(token_row, 1, 100, [{"channel_id": "channel_1", "raw_value": 1824}], workout_id)
    second = mobile.store_sensor_sample(token_row, 3, 200, [{"channel_id": "channel_1", "raw_value": 1825}], workout_id)
    assert first["missing_sequences"] == 0 and second["missing_sequences"] == 1
    restarted = MobileStore(mobile.db_path, mobile.data_dir, "invite-code")
    assert restarted.sensor_status(alice["id"])[0]["last_sequence"] == 3
    assert restarted.sensor_status(bob["id"]) == []
    with pytest.raises(HTTPException):
        restarted.store_sensor_sample(token_row, 4, 300, [{"channel_id": "channel_1", "raw_value": 1}], restarted.create_workout(bob["id"])[0])
    restarted.revoke_pairing(pairing["pairing_id"], alice["id"])
    with pytest.raises(HTTPException):
        restarted.pairing_for_token(pairing["token"])


def test_pairing_upsert_keeps_samples_and_revoke_deletes(tmp_path):
    mobile = store(tmp_path)
    user = mobile.register("sensor_user", "correct-horse-1", "correct-horse-1", "invite-code")
    workout_id, _ = mobile.create_workout(user["id"])
    first = mobile.create_pairing(user["id"], "esp32-demo-01")
    mobile.store_sensor_sample(mobile.pairing_for_token(first["token"]), 1, 100, [], None)
    second = mobile.create_pairing(user["id"], "esp32-demo-01", workout_id=workout_id)
    assert second["pairing_id"] != first["pairing_id"]
    assert second["sequence"] == 0
    with pytest.raises(HTTPException):
        mobile.pairing_for_token(first["token"])
    with mobile.connect() as db:
        row = db.execute("SELECT * FROM sensor_pairings WHERE user_id=?", (user["id"],)).fetchone()
        assert row["id"] == second["pairing_id"] and row["workout_id"] == workout_id
        assert db.execute("SELECT pairing_id FROM sensor_samples").fetchone()[0] == second["pairing_id"]
    mobile.store_sensor_sample(mobile.pairing_for_token(second["token"]), 1, 200, [], workout_id)
    with mobile.connect() as db:
        assert [row[0] for row in db.execute("SELECT device_sequence FROM sensor_samples ORDER BY sequence")] == [1, 1]
    mobile.revoke_pairing(second["pairing_id"], user["id"])
    with mobile.connect() as db:
        assert db.execute("SELECT count(*) FROM sensor_pairings").fetchone()[0] == 0
    assert mobile.create_pairing(user["id"], "esp32-demo-01")["pairing_id"]


def test_pairing_ttl_and_receiving_window(tmp_path, monkeypatch):
    monkeypatch.setenv("ULIANA_PAIRING_TTL_MINUTES", "180")
    mobile = store(tmp_path)
    user = mobile.register("sensor_user", "correct-horse-1", "correct-horse-1", "invite-code")
    pairing = mobile.create_pairing(user["id"], "esp32-demo-01")
    assert pairing["expires_in_seconds"] == 10800
    assert pairing["sequence"] == 0
    assert mobile.sensor_status(user["id"])[0]["state"] == "Paired"
    mobile.store_sensor_sample(mobile.pairing_for_token(pairing["token"]), 1, 100, [], None)
    assert mobile.sensor_status(user["id"])[0]["state"] == "Receiving data"
    assert mobile.sensor_status(user["id"])[0]["last_sequence"] == 1
    with mobile.connect() as db:
        db.execute("UPDATE sensor_pairings SET last_seen_at=? WHERE id=?",
                   ((datetime.now(timezone.utc) - timedelta(seconds=61)).isoformat(), pairing["pairing_id"]))
    assert mobile.sensor_status(user["id"])[0]["state"] == "Connection lost"
