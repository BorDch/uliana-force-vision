"""SQLite-backed authentication and ownership for the mobile pilot."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request, Response

USERNAME = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
SESSION_SECONDS = 60 * 60 * 24 * 30
LOGGER = logging.getLogger(__name__)


class MobileStore:
    def __init__(self, db_path: Path, data_dir: Path, pilot_code: str):
        self.db_path = db_path.resolve()
        self.data_dir = data_dir.resolve()
        self.pilot_code = pilot_code
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "users").mkdir(parents=True, exist_ok=True)
        self._attempts: dict[str, list[float]] = {}
        self.init_schema()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_schema(self) -> None:
        with self.connect() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, username TEXT NOT NULL, username_key TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, created_at TEXT NOT NULL
              );
              CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf_hash TEXT NOT NULL, expires_at INTEGER NOT NULL, created_at TEXT NOT NULL
              );
              CREATE TABLE IF NOT EXISTS workout_sessions (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status TEXT NOT NULL, exercise TEXT NOT NULL, variation TEXT NOT NULL,
                relative_path TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                error TEXT
              );
              CREATE INDEX IF NOT EXISTS workout_user_created ON workout_sessions(user_id, created_at DESC);
              CREATE TABLE IF NOT EXISTS processing_jobs (
                id TEXT PRIMARY KEY, workout_id TEXT NOT NULL REFERENCES workout_sessions(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
              );
              CREATE TABLE IF NOT EXISTS sensor_pairings (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                device_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
                expires_at INTEGER NOT NULL, revoked_at TEXT, last_seen_at TEXT,
                UNIQUE(user_id, device_id)
              );
              CREATE TABLE IF NOT EXISTS sensor_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pairing_id TEXT NOT NULL REFERENCES sensor_pairings(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                workout_id TEXT REFERENCES workout_sessions(id) ON DELETE SET NULL,
                device_id TEXT NOT NULL, sequence INTEGER NOT NULL, device_time_ms INTEGER NOT NULL,
                channels_json TEXT NOT NULL, received_at TEXT NOT NULL, missing_before INTEGER NOT NULL DEFAULT 0,
                UNIQUE(pairing_id, sequence)
              );
              CREATE INDEX IF NOT EXISTS sensor_samples_user_received ON sensor_samples(user_id, received_at DESC);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(sensor_pairings)")}
            if "workout_id" not in columns:
                db.execute("ALTER TABLE sensor_pairings ADD COLUMN workout_id TEXT REFERENCES workout_sessions(id) ON DELETE SET NULL")
            if "sequence_offset" not in columns:
                db.execute("ALTER TABLE sensor_pairings ADD COLUMN sequence_offset INTEGER NOT NULL DEFAULT 0")
            sample_columns = {row[1] for row in db.execute("PRAGMA table_info(sensor_samples)")}
            if "device_sequence" not in sample_columns:
                db.execute("ALTER TABLE sensor_samples ADD COLUMN device_sequence INTEGER")
                db.execute("UPDATE sensor_samples SET device_sequence=sequence")

    @staticmethod
    def password_hash(password: str) -> str:
        salt = secrets.token_bytes(16)
        derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return f"scrypt$16384$8$1${salt.hex()}${derived.hex()}"

    @staticmethod
    def password_ok(password: str, encoded: str) -> bool:
        try:
            _, n, r, p, salt, expected = encoded.split("$")
            actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
            return hmac.compare_digest(actual, bytes.fromhex(expected))
        except (ValueError, TypeError):
            return False

    def rate_limit(self, key: str, limit: int = 8, window: int = 300) -> None:
        now = time.monotonic()
        recent = [value for value in self._attempts.get(key, []) if now - value < window]
        if len(recent) >= limit:
            raise HTTPException(429, "Too many attempts. Please try again later.")
        recent.append(now)
        self._attempts[key] = recent

    def register(self, username: str, password: str, confirmation: str, invitation: str) -> sqlite3.Row:
        username = username.strip()
        if not self.pilot_code or not hmac.compare_digest(invitation, self.pilot_code):
            raise HTTPException(403, "The pilot invitation code is invalid.")
        if not USERNAME.fullmatch(username):
            raise HTTPException(400, "Username must be 3–32 characters using letters, numbers, dot, dash, or underscore.")
        if len(password) < 10:
            raise HTTPException(400, "Password must contain at least 10 characters.")
        if password != confirmation:
            raise HTTPException(400, "Passwords do not match.")
        user_id, now = str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()
        try:
            with self.connect() as db:
                db.execute("INSERT INTO users VALUES (?,?,?,?,?)", (user_id, username, username.casefold(), self.password_hash(password), now))
                return db.execute("SELECT id,username FROM users WHERE id=?", (user_id,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "That username is already in use.") from exc

    def authenticate(self, username: str, password: str) -> sqlite3.Row:
        with self.connect() as db:
            user = db.execute("SELECT * FROM users WHERE username_key=?", (username.strip().casefold(),)).fetchone()
        if not user or not self.password_ok(password, user["password_hash"]):
            raise HTTPException(401, "Incorrect username or password.")
        return user

    @staticmethod
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def issue_session(self, response: Response, user_id: str, secure: bool) -> None:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("INSERT INTO auth_sessions VALUES (?,?,?,?,?)", (self.digest(token), user_id, self.digest(csrf), int(time.time()) + SESSION_SECONDS, now))
        response.set_cookie("uliana_session", token, max_age=SESSION_SECONDS, httponly=True, secure=secure, samesite="lax", path="/")
        response.set_cookie("uliana_csrf", csrf, max_age=SESSION_SECONDS, httponly=False, secure=secure, samesite="lax", path="/")

    def current_user(self, request: Request, csrf: bool = False) -> sqlite3.Row:
        token = request.cookies.get("uliana_session", "")
        with self.connect() as db:
            row = db.execute("SELECT u.id,u.username,s.csrf_hash,s.expires_at FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?", (self.digest(token),)).fetchone() if token else None
        if not row or row["expires_at"] < int(time.time()):
            raise HTTPException(401, "Sign in to continue.")
        if csrf:
            cookie = request.cookies.get("uliana_csrf", "")
            header = request.headers.get("x-csrf-token", "")
            if not cookie or not hmac.compare_digest(cookie, header) or not hmac.compare_digest(self.digest(cookie), row["csrf_hash"]):
                raise HTTPException(403, "Security check failed. Refresh the page and try again.")
        return row

    def revoke(self, request: Request, response: Response) -> None:
        token = request.cookies.get("uliana_session", "")
        if token:
            with self.connect() as db: db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (self.digest(token),))
        response.delete_cookie("uliana_session", path="/"); response.delete_cookie("uliana_csrf", path="/")

    def create_workout(self, user_id: str) -> tuple[str, Path]:
        workout_id = str(uuid.uuid4())
        relative = Path("users") / user_id / "sessions" / workout_id
        target = (self.data_dir / relative).resolve()
        target.relative_to(self.data_dir)
        target.mkdir(parents=True, exist_ok=False)
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("INSERT INTO workout_sessions VALUES (?,?,?,?,?,?,?,?,?)", (workout_id, user_id, "created", "push-up", "standard", str(relative), now, now, None))
        return workout_id, target

    def workout(self, workout_id: str, user_id: str) -> tuple[sqlite3.Row, Path]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM workout_sessions WHERE id=? AND user_id=?", (workout_id, user_id)).fetchone()
        if not row: raise HTTPException(404, "Session not found")
        target = (self.data_dir / row["relative_path"]).resolve()
        target.relative_to(self.data_dir)
        if not target.is_dir(): raise HTTPException(404, "Session not found")
        return row, target

    def set_status(self, workout_id: str, status: str, error: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("UPDATE workout_sessions SET status=?,updated_at=?,error=? WHERE id=?", (status, now, error, workout_id))
            db.execute("UPDATE processing_jobs SET status=?,updated_at=? WHERE workout_id=?", (status, now, workout_id))

    def create_job(self, workout_id: str, user_id: str) -> str:
        job_id, now = str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("INSERT INTO processing_jobs VALUES (?,?,?,?,?,?)", (job_id, workout_id, user_id, "queued", now, now))
        return job_id

    def list_workouts(self, user_id: str) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute("SELECT * FROM workout_sessions WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()

    def job(self, job_id: str, user_id: str) -> sqlite3.Row:
        with self.connect() as db: row = db.execute("SELECT * FROM processing_jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
        if not row: raise HTTPException(404, "Processing job not found")
        return row

    def delete_account(self, user_id: str) -> None:
        root = (self.data_dir / "users" / user_id).resolve(); root.relative_to(self.data_dir)
        with self.connect() as db: db.execute("DELETE FROM users WHERE id=?", (user_id,))
        if root.is_dir(): shutil.rmtree(root)

    def create_pairing(self, user_id: str, device_id: str, ttl_seconds: int | None = None, workout_id: str | None = None) -> dict:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", device_id):
            raise HTTPException(400, "Device ID must be 3–64 letters, numbers, dots, dashes, or underscores.")
        if workout_id: self.workout(workout_id, user_id)
        if ttl_seconds is None:
            try:
                ttl_minutes = int(os.environ.get("ULIANA_PAIRING_TTL_MINUTES", "15"))
            except ValueError as exc:
                raise RuntimeError("ULIANA_PAIRING_TTL_MINUTES must be a positive integer") from exc
            if ttl_minutes <= 0:
                raise RuntimeError("ULIANA_PAIRING_TTL_MINUTES must be a positive integer")
            ttl_seconds = ttl_minutes * 60
        token, pairing_id = secrets.token_urlsafe(32), str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            previous = db.execute("SELECT id FROM sensor_pairings WHERE user_id=? AND device_id=?", (user_id, device_id)).fetchone()
            sequence_offset = (db.execute("SELECT COALESCE(MAX(sequence),0) FROM sensor_samples WHERE pairing_id=?", (previous["id"],)).fetchone()[0]
                               if previous else 0)
            # Samples retain their reference when the pairing gets a fresh ID.
            db.execute("PRAGMA defer_foreign_keys=ON")
            db.execute("""INSERT INTO sensor_pairings(id,user_id,device_id,token_hash,created_at,expires_at,workout_id)
                          VALUES(?,?,?,?,?,?,?)
                          ON CONFLICT(user_id, device_id) DO UPDATE SET
                            id=excluded.id, token_hash=excluded.token_hash,
                            created_at=excluded.created_at, expires_at=excluded.expires_at,
                            workout_id=excluded.workout_id, revoked_at=NULL, last_seen_at=NULL,
                            sequence_offset=?""",
                       (pairing_id, user_id, device_id, self.digest(token), now, int(time.time()) + ttl_seconds, workout_id, sequence_offset))
            if previous:
                db.execute("UPDATE sensor_samples SET pairing_id=? WHERE pairing_id=?", (pairing_id, previous["id"]))
        return {"pairing_id": pairing_id, "device_id": device_id, "token": token, "expires_in_seconds": ttl_seconds, "sequence": 0}

    def revoke_pairing(self, pairing_id: str, user_id: str) -> None:
        with self.connect() as db:
            changed = db.execute("DELETE FROM sensor_pairings WHERE id=? AND user_id=?", (pairing_id, user_id)).rowcount
        if not changed: raise HTTPException(404, "Pairing not found")

    def pairing_for_token(self, token: str) -> sqlite3.Row:
        token_hash = self.digest(token)
        with self.connect() as db:
            row = db.execute("SELECT * FROM sensor_pairings WHERE token_hash=?", (token_hash,)).fetchone()
        LOGGER.debug("pairing lookup digest=%s row_found=%s database=%s", token_hash, bool(row), self.db_path)
        if not row or row["revoked_at"] or row["expires_at"] < int(time.time()):
            raise HTTPException(401, "Pairing token is invalid or expired.")
        return row

    def store_sensor_sample(self, pairing: sqlite3.Row, sequence: int, device_time_ms: int, channels: list[dict], workout_id: str | None) -> dict:
        workout_id = workout_id or pairing["workout_id"]
        if workout_id: self.workout(workout_id, pairing["user_id"])
        received = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            prior = db.execute("SELECT MAX(device_sequence) FROM sensor_samples WHERE pairing_id=? AND sequence>?",
                               (pairing["id"], pairing["sequence_offset"])).fetchone()[0]
            if prior is not None and sequence <= prior: raise HTTPException(409, "Sequence must increase.")
            missing = max(0, sequence - prior - 1) if prior is not None else 0
            db.execute("INSERT INTO sensor_samples(pairing_id,user_id,workout_id,device_id,sequence,device_sequence,device_time_ms,channels_json,received_at,missing_before) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (pairing["id"], pairing["user_id"], workout_id, pairing["device_id"], pairing["sequence_offset"] + sequence, sequence, device_time_ms, json.dumps(channels, separators=(",", ":")), received, missing))
            db.execute("UPDATE sensor_pairings SET last_seen_at=? WHERE id=?", (received, pairing["id"]))
        return {"accepted": True, "sequence": sequence, "missing_sequences": missing, "received_at": received}

    def sensor_status(self, user_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("""SELECT p.id,p.device_id,p.workout_id,p.expires_at,p.revoked_at,p.last_seen_at,
              (SELECT device_sequence FROM sensor_samples s WHERE s.pairing_id=p.id AND s.sequence>p.sequence_offset ORDER BY sequence DESC LIMIT 1) last_sequence,
              (SELECT channels_json FROM sensor_samples s WHERE s.pairing_id=p.id AND s.sequence>p.sequence_offset ORDER BY sequence DESC LIMIT 1) channels_json
              FROM sensor_pairings p WHERE p.user_id=? ORDER BY p.created_at DESC""", (user_id,)).fetchall()
        now = datetime.now(timezone.utc)
        output=[]
        for row in rows:
            age = (now - datetime.fromisoformat(row["last_seen_at"])).total_seconds() if row["last_seen_at"] else None
            state = "Not connected" if row["revoked_at"] or row["expires_at"] < int(time.time()) else "Paired" if age is None else "Receiving data" if age <= 60 else "Connection lost"
            output.append({"pairing_id":row["id"],"device_id":row["device_id"],"workout_session_id":row["workout_id"],"state":state,"last_seen_at":row["last_seen_at"],"last_sequence":row["last_sequence"],"channels":json.loads(row["channels_json"]) if row["channels_json"] else []})
        return output


def request_is_secure(request: Request) -> bool:
    if request.url.scheme == "https": return True
    if os.environ.get("ULIANA_TRUST_PROXY") == "1":
        return request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower() == "https"
    return False


import shutil  # kept last to make destructive use conspicuous
