#!/usr/bin/env python3
"""Local-only presentation API for recorded ULIANA sessions."""
from __future__ import annotations

import json
import logging
import hmac
import mimetypes
import os
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, Response as AudioResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from uliana.config import load_config
from uliana.contracts.models import RepetitionInterval
from uliana.reporting.feedback_policy import compose_feedback
from uliana.reporting.research_preview import build_research_preview
from uliana.reporting.coach_summary import build_coach_facts, coach_summary, configured_provider
from uliana.video.processing import observation_from_dict
from scripts.mobile_auth import MobileStore, request_is_secure
from scripts.hand_width import camera_measurement, classify_hand_width, sensor_hand_width_cm
from scripts.review_overlay import review_moments
from scripts.tts_service import synthesize_wav

ROOT = Path(__file__).resolve().parents[1]
STORE = Path(os.environ.get("ULIANA_DATA_DIR", ROOT / "data" / "demo_sessions")).resolve()
WEB = Path(os.environ.get("ULIANA_WEB_DIR", ROOT / "uliana-demo" / "dist" / "client")).resolve()
PYTHON = ROOT / ".venv-video" / "bin" / "python"
MODEL = ROOT / "models" / "pose_landmarker_full.task"
CONFIG = ROOT / "configs" / "video_processing.json"
MAX_BYTES = 500 * 1024 * 1024
ALLOWED = {".mov", ".mp4", ".m4v", ".webm"}
LOCK = threading.Lock()
RUNTIME_MODE = os.environ.get("ULIANA_MODE", "site").strip().lower()
RUNTIME_PROFILE = os.environ.get("ULIANA_PROFILE_ID", "local-default").strip()
if RUNTIME_MODE not in {"site", "app", "mobile"}:
    raise RuntimeError("ULIANA_MODE must be 'site', 'app', or 'mobile'")
if not RUNTIME_PROFILE:
    raise RuntimeError("ULIANA_PROFILE_ID must not be empty")
MOBILE = MobileStore(Path(os.environ.get("ULIANA_AUTH_DB", STORE / "mobile.sqlite3")), STORE, os.environ.get("ULIANA_PILOT_CODE", "")) if RUNTIME_MODE == "mobile" else None

app = FastAPI(title="ULIANA local demo", docs_url=None, redoc_url=None)


@app.get("/api/runtime")
def runtime() -> dict:
    """Tell the shared static frontend which local presentation shell to use."""
    return {"mode": RUNTIME_MODE, "max_upload_bytes": MAX_BYTES,
            "formats": sorted(ALLOWED), "accounts": RUNTIME_MODE == "mobile"}


class NewSession(BaseModel):
    exercise: str
    consent: bool
    profile_id: str = "local-default"
    exercise_variation: str = "standard"
    exercise_type: str = "standard"


# Landmark plans for future variant assessment. Only standard uses the frozen camera pipeline.
PUSH_UP_TYPE_LANDMARKS = {
    "standard": (11, 12, 23, 24, 27, 28, 13, 14),
    "diamond": (11, 12, 23, 24, 27, 28, 13, 14, 15, 16),
    "wide": (11, 12, 23, 24, 27, 28, 15, 16),
    "incline": (11, 12, 23, 24, 27, 28, 15, 16),
    "decline": (11, 12, 23, 24, 27, 28),
}

class RegisterBody(BaseModel):
    username: str; password: str; password_confirmation: str; invitation_code: str

class LoginBody(BaseModel):
    username: str; password: str

class DeleteAccountBody(BaseModel):
    password: str; confirmation: str

class TTSBody(BaseModel):
    text: str
    voice: str = "af_heart"
    session_id: str | None = None

class PairingBody(BaseModel):
    device_id: str = Field(min_length=3, max_length=64)
    workout_session_id: str | None = None

class ShoulderCalibrationBody(BaseModel):
    shoulder_width_norm: float | None = None

class SensorChannel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    channel_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,32}$")
    raw_value: int = Field(ge=-2147483648, le=2147483647)

class TelemetryBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: int
    device_id: str = Field(min_length=3, max_length=64)
    sequence: int = Field(ge=0, le=2147483647)
    device_time_ms: int = Field(ge=0, le=9223372036854775807)
    channels: list[SensorChannel] = Field(min_length=16, max_length=16)
    baseline: dict[str, int] | None = None
    workout_session_id: str | None = None

def mobile_user(request: Request, csrf: bool = False):
    if MOBILE is None: raise HTTPException(404, "Not found")
    return MOBILE.current_user(request, csrf=csrf)

@app.post("/api/profile/calibrate-shoulders")
def calibrate_shoulders(body: ShoulderCalibrationBody, request: Request) -> dict:
    user = mobile_user(request, csrf=True)
    if body.shoulder_width_norm is None or not 0 < body.shoulder_width_norm <= 1:
        raise HTTPException(400, "shoulder_width_norm must be between 0 and 1.")
    saved = MOBILE.save_shoulder_calibration(user["id"], body.shoulder_width_norm)
    return {"shoulder_width_cm": saved["shoulder_width_cm"], "saved": True}

@app.post("/api/tts/synthesize")
def tts_synthesize(body: TTSBody, request: Request):
    user = mobile_user(request, csrf=True)
    if not body.text.strip(): raise HTTPException(400, "Text is required.")
    if len(body.text) > 500: raise HTTPException(400, "Text exceeds 500 characters.")
    if body.voice not in {"af_heart", "af_bella", "af_sarah"}: raise HTTPException(400, "Unsupported voice.")
    if body.session_id: MOBILE.workout(body.session_id, user["id"])
    MOBILE.rate_limit(f"tts:{user['id']}", limit=20, window=60)
    logging.getLogger("uliana.tts").info("TTS request user=%s session=%s length=%d", user["id"], body.session_id or "none", len(body.text))
    try:
        wav = synthesize_wav(body.text, body.voice)
    except Exception as exc:
        logging.getLogger("uliana.tts").exception("TTS generation failed")
        raise HTTPException(503, "Audio unavailable.") from exc
    return AudioResponse(content=wav, media_type="audio/wav", headers={"Cache-Control": "private, no-store"})

@app.post("/api/sensors/pairings", status_code=200)
def create_sensor_pairing(body: PairingBody, request: Request) -> dict:
    user = mobile_user(request, csrf=True)
    MOBILE.rate_limit(f"pair:{user['id']}", limit=pairing_rate_limit(), window=60)
    return MOBILE.create_pairing(user["id"], body.device_id, workout_id=body.workout_session_id)

def pairing_rate_limit() -> int:
    value = os.environ.get("ULIANA_RATE_LIMIT_PAIRING", "5")
    try:
        limit = int(value)
        if limit > 0: return limit
    except ValueError:
        pass
    raise RuntimeError("ULIANA_RATE_LIMIT_PAIRING must be a positive integer (requests per minute)")

@app.get("/api/sensors")
def sensor_status(request: Request) -> dict:
    user = mobile_user(request)
    return {"devices": MOBILE.sensor_status(user["id"]), "label": "Raw experimental sensor signal"}

@app.delete("/api/sensors/pairings/{pairing_id}", status_code=204)
def revoke_sensor_pairing(pairing_id: str, request: Request):
    user = mobile_user(request, csrf=True)
    MOBILE.revoke_pairing(pairing_id, user["id"])
    return None

@app.post("/api/sensor/ingest")
@app.post("/api/sensors/telemetry")
async def ingest_sensor_telemetry(request: Request) -> dict:
    if MOBILE is None: raise HTTPException(404, "Not found")
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer ") or not auth[7:].strip(): raise HTTPException(401, "Pairing token required.")
    token = auth[7:].strip()
    pairing = MOBILE.pairing_for_token(token)
    try:
        length = int(request.headers.get("content-length", "0") or 0)
    except ValueError as exc:
        raise HTTPException(400, "Invalid content length.") from exc
    if length > 65_536: raise HTTPException(413, "Telemetry payload is too large.")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65_536: raise HTTPException(413, "Telemetry payload is too large.")
    try: body = TelemetryBody.model_validate_json(bytes(raw))
    except Exception as exc: raise HTTPException(400, "Malformed telemetry payload.") from exc
    if body.schema_version != 1: raise HTTPException(400, "Unsupported telemetry schema version.")
    if {item.channel_id for item in body.channels} != {f"channel_{i}" for i in range(16)}:
        raise HTTPException(400, "Exactly channel_0 through channel_15 are required.")
    if body.baseline is not None and set(body.baseline) != {f"channel_{i}" for i in range(16)}:
        raise HTTPException(400, "Baseline must include channel_0 through channel_15.")
    if not hmac.compare_digest(pairing["device_id"], body.device_id): raise HTTPException(403, "Device does not match this pairing.")
    MOBILE.rate_limit(f"ingest:{pairing['id']}", limit=240, window=60)
    return MOBILE.store_sensor_sample(pairing, body.sequence, body.device_time_ms, [item.model_dump() for item in body.channels], body.workout_session_id, body.baseline)

def owned_folder(request: Request, session_id: str, csrf: bool = False) -> Path:
    if MOBILE is None: return folder(session_id)
    user = mobile_user(request, csrf=csrf)
    return MOBILE.workout(session_id, user["id"])[1]

@app.get("/api/sessions/{session_id}/hand-width")
def hand_width_for_session(session_id: str, request: Request) -> dict:
    target = owned_folder(request, session_id)
    user = mobile_user(request) if MOBILE is not None else None
    calibration = MOBILE.shoulder_calibration(user["id"]) if MOBILE is not None else None
    shoulder_width_cm = float(calibration["shoulder_width_cm"]) if calibration else 40.0
    preferred_timestamp = _preferred_review_timestamp(target)
    camera = camera_measurement(target / "analysis" / "video_observations.jsonl", preferred_timestamp)
    device = None
    if MOBILE is not None:
        device = next(
            (item for item in MOBILE.sensor_status(user["id"])
             if item.get("workout_session_id") == session_id),
            None,
        )
    sensor_width = sensor_hand_width_cm(device)
    response = {
        "session_id": session_id,
        "shoulder_width_cm": shoulder_width_cm,
        "hand_width_cm": None,
        "deviation_cm": None,
        "classification": None,
        "recommendation": None,
        "source": "camera",
        "sensor_hand_width_cm": sensor_width,
        "sensor_camera_agree": None,
        "calibration_used": calibration is not None,
        "expected_shoulders": camera["expected_shoulders"] if camera else None,
    }
    if camera is None:
        return response
    reference_norm = calibration.get("shoulder_width_norm") if calibration else camera["shoulder_width_norm"]
    if not isinstance(reference_norm, (int, float)) or reference_norm <= 0:
        return response
    measured = round(camera["hand_width_norm"] / reference_norm * shoulder_width_cm, 1)
    deviation = round(measured - shoulder_width_cm, 1)
    classification, recommendation = classify_hand_width(deviation)
    response.update({
        "hand_width_cm": measured,
        "deviation_cm": deviation,
        "classification": classification,
        "recommendation": recommendation,
        "sensor_camera_agree": abs(sensor_width - measured) <= 5 if sensor_width is not None else None,
    })
    return response


def _preferred_review_timestamp(target: Path) -> int | None:
    moments = review_moments(target).get("moments", [])
    if moments:
        value = moments[0].get("timestamp_ms")
        if isinstance(value, int):
            return value
    result_path = target / "analysis" / "session_result.json"
    if result_path.is_file():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        intervals = result.get("repetition_intervals") or []
        if intervals and isinstance(intervals[0].get("bottom_ms"), int):
            return intervals[0]["bottom_ms"]
    return None

@app.post("/api/auth/register", status_code=201)
def register(body: RegisterBody, request: Request, response: Response) -> dict:
    if MOBILE is None: raise HTTPException(404, "Not found")
    MOBILE.rate_limit(f"register:{request.client.host if request.client else 'unknown'}:{body.username.casefold()}")
    user = MOBILE.register(body.username, body.password, body.password_confirmation, body.invitation_code)
    MOBILE.issue_session(response, user["id"], request_is_secure(request))
    return {"username": user["username"]}

@app.post("/api/auth/login")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    if MOBILE is None: raise HTTPException(404, "Not found")
    MOBILE.rate_limit(f"login:{request.client.host if request.client else 'unknown'}:{body.username.casefold()}")
    user = MOBILE.authenticate(body.username, body.password)
    MOBILE.issue_session(response, user["id"], request_is_secure(request))
    return {"username": user["username"]}

@app.get("/api/auth/me")
def me(request: Request) -> dict:
    user = mobile_user(request); return {"username": user["username"]}

@app.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response):
    mobile_user(request, csrf=True); MOBILE.revoke(request, response); return None

@app.delete("/api/auth/account", status_code=204)
def delete_account(body: DeleteAccountBody, request: Request, response: Response):
    user = mobile_user(request, csrf=True)
    if body.confirmation != "DELETE": raise HTTPException(400, "Type DELETE to confirm.")
    verified = MOBILE.authenticate(user["username"], body.password)
    MOBILE.delete_account(verified["id"]); MOBILE.revoke(request, response); return None


def folder(session_id: str) -> Path:
    if not session_id or any(c not in "0123456789abcdef-" for c in session_id):
        raise HTTPException(404, "Session not found")
    target = STORE / session_id
    if not target.is_dir():
        raise HTTPException(404, "Session not found")
    return target


def read_meta(target: Path) -> dict:
    return json.loads((target / "metadata.json").read_text(encoding="utf-8"))


def write_meta(target: Path, data: dict) -> None:
    with LOCK:
        tmp = target / "metadata.tmp"
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(target / "metadata.json")


def update(target: Path, **fields: object) -> dict:
    data = read_meta(target); data.update(fields); write_meta(target, data)
    if MOBILE is not None and "status" in fields: MOBILE.set_status(target.name, str(fields["status"]), str(fields.get("error")) if fields.get("error") else None)
    return data


def compatible_comparison(target: Path, current: dict) -> dict:
    candidates = []
    if MOBILE is not None:
        with MOBILE.connect() as db:
            owner = db.execute("SELECT user_id FROM workout_sessions WHERE id=?", (target.name,)).fetchone()
        others = [(STORE / row["relative_path"]).resolve() for row in MOBILE.list_workouts(owner["user_id"])] if owner else []
    else:
        others = list(STORE.iterdir()) if STORE.is_dir() else []
    for other in others:
        if other == target or not other.is_dir() or not (other / "metadata.json").is_file() or not (other / "analysis" / "session_result.json").is_file():
            continue
        meta = read_meta(other)
        if meta.get("status") != "completed" or meta.get("created_at", "") >= current.get("created_at", ""):
            continue
        if (meta.get("profile_id", "local-default"), meta.get("exercise"), meta.get("exercise_variation", "standard")) != (current.get("profile_id", "local-default"), current.get("exercise"), current.get("exercise_variation", "standard")):
            continue
        previous = {**json.loads((other / "analysis" / "session_result.json").read_text(encoding="utf-8")), **meta}
        candidates.append(previous)
    if not candidates:
        return {"available": False, "reason": "no_previous_compatible_session"}
    previous = max(candidates, key=lambda item: item.get("created_at", ""))
    if (previous.get("detected_viewpoint") or {}).get("value") != (current.get("detected_viewpoint") or {}).get("value"):
        return {"available": False, "reason": "camera_setup_changed"}
    def flagged(value: dict, condition: str) -> int:
        return len({item.get("rep_id") for item in value.get("assessments", []) if item.get("condition") == condition and item.get("result") == "condition_detected" and item.get("rep_id") is not None})
    before, now = previous.get("repetition_count"), current.get("repetition_count")
    summary = f"Previous comparable session: {before if before is not None else 'count unavailable'} repetitions; this session: {now if now is not None else 'count unavailable'}."
    return {"available": True, "previous_completed_repetitions": before, "completed_repetitions_change": now - before if now is not None and before is not None else None, "body_alignment_review_change": flagged(current, "body_alignment_deviation") - flagged(previous, "body_alignment_deviation"), "range_of_motion_review_change": flagged(current, "push_up_depth_proxy") - flagged(previous, "push_up_depth_proxy"), "summary": summary}


def public_result(target: Path) -> dict:
    meta = read_meta(target)
    result_file = target / "analysis" / "session_result.json"
    result = json.loads(result_file.read_text(encoding="utf-8")) if result_file.exists() else {}
    metrics_file = target / "analysis" / "camera_metrics.json"
    metrics = json.loads(metrics_file.read_text(encoding="utf-8")) if metrics_file.exists() else {}
    preview_file = target / "analysis" / "research_preview.json"
    preview = json.loads(preview_file.read_text(encoding="utf-8")) if preview_file.exists() else {}
    payload = {**result, **meta}
    if result:
        payload["research_preview"] = preview
        payload["feedback_report"] = compose_feedback(result, metrics, preview)
        comparison = compatible_comparison(target, payload)
        facts = build_coach_facts(payload, comparison, smart_mat_connected=False)
        try:
            provider = configured_provider()
        except Exception:
            provider = None
        payload["coach_summary"] = coach_summary(facts, target.name, target / "analysis" / "coach_summary.json", provider)
    elif meta.get("message"): payload["feedback"] = meta["message"]
    if (target / "annotated.mp4").exists(): payload["annotated_video_url"] = f"/api/sessions/{target.name}/annotated-video"
    if (target / "source.mp4").exists(): payload["source_video_url"] = f"/api/sessions/{target.name}/source-video"
    return payload


@app.post("/api/sessions", status_code=201)
def create_session(body: NewSession, request: Request) -> dict:
    if not body.consent: raise HTTPException(400, "Consent is required")
    if body.exercise != "push-up" and RUNTIME_MODE == "mobile": raise HTTPException(400, "Only push-up analysis is available.")
    if body.exercise not in {"push-up", "pull-up"}: raise HTTPException(400, "Unsupported exercise")
    if body.exercise_type not in PUSH_UP_TYPE_LANDMARKS: raise HTTPException(400, "Unsupported push-up type")
    if body.exercise != "push-up" and body.exercise_type != "standard": raise HTTPException(400, "Push-up type requires a push-up session")
    if MOBILE is not None:
        user = mobile_user(request, csrf=True); session_id, target = MOBILE.create_workout(user["id"]); profile_id = user["id"]
    else:
        session_id = str(uuid.uuid4()); target = STORE / session_id; target.mkdir(parents=True, exist_ok=False); profile_id = body.profile_id
    meta = {"session_id": session_id, "profile_id": profile_id, "exercise": body.exercise, "exercise_variation": body.exercise_variation, "exercise_type": body.exercise_type, "created_at": datetime.now(timezone.utc).isoformat(), "status": "created"}
    write_meta(target, meta); return meta


@app.post("/api/sessions/{session_id}/video")
async def upload_video(session_id: str, request: Request, video: UploadFile = File(...)) -> dict:
    target = owned_folder(request, session_id, csrf=MOBILE is not None); suffix = Path(video.filename or "").suffix.lower()
    content_type = video.content_type or mimetypes.guess_type(video.filename or "")[0] or ""
    if suffix not in ALLOWED or not content_type.startswith("video/"): raise HTTPException(415, "Choose a supported video file (MOV, MP4, M4V, or WebM).")
    update(target, status="uploading")
    incoming = target / f"incoming{suffix}"; total = 0
    try:
        with incoming.open("wb") as output:
            while chunk := await video.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_BYTES: raise HTTPException(413, "Video exceeds the 500 MB demo limit.")
                output.write(chunk)
        if total < 1024: raise HTTPException(422, "The uploaded video is empty or invalid.")
        probe = subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=codec_type:format=duration","-of","json",str(incoming)], capture_output=True, text=True, timeout=30)
        probe_data = {}
        try: probe_data = json.loads(probe.stdout); duration = float(probe_data["format"]["duration"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError): duration = 0.0
        if probe.returncode or not probe_data.get("streams") or duration <= 0: raise HTTPException(422, "The recording could not be decoded as video.")
        subprocess.run(["ffmpeg","-y","-i",str(incoming),"-map_metadata","0","-vf","scale='min(1280,iw)':-2","-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p","-movflags","+faststart","-an",str(target/"source.mp4")], check=True, capture_output=True, timeout=300)
        meta = update(target, status="completed" if read_meta(target)["exercise"] == "pull-up" else "queued", size_bytes=total, duration_seconds=duration,
          message="Recording saved for experimental pull-up analysis. Automated results are not available yet." if read_meta(target)["exercise"] == "pull-up" else None)
        incoming.unlink(missing_ok=True); return meta
    except HTTPException: incoming.unlink(missing_ok=True); update(target,status="failed"); raise
    except Exception as exc: incoming.unlink(missing_ok=True); update(target,status="failed",error="Video decoding or normalization failed"); raise HTTPException(422,"Video decoding or normalization failed.") from exc


def run_analysis(target: Path) -> None:
    try:
        analysis = target / "analysis"; analysis.mkdir(exist_ok=True)
        update(target, status="processing_pose")
        subprocess.run([str(PYTHON),str(ROOT/"scripts/inspect_video_session.py"),str(target/"source.mp4"),"--session-id",target.name,"--output-dir",str(analysis),"--model",str(MODEL),"--config",str(CONFIG),"--no-overlay"], check=True, cwd=ROOT, timeout=1800)
        update(target, status="counting_repetitions")
        subprocess.run([str(PYTHON),str(ROOT/"scripts/analyze_camera_session.py"),"--video-observations",str(analysis/"video_observations.jsonl"),"--video-summary",str(analysis/"video_summary.json"),"--output-dir",str(analysis),"--video",str(target/"source.mp4"),"--config",str(CONFIG),"--json"], check=True, cwd=ROOT, timeout=900)
        observations = [observation_from_dict(json.loads(line)) for line in (analysis/"video_observations.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        summary = json.loads((analysis/"video_summary.json").read_text(encoding="utf-8"))
        frozen = json.loads((analysis/"session_result.json").read_text(encoding="utf-8"))
        intervals = [RepetitionInterval(**item) for item in frozen.get("repetition_intervals", [])]
        viewpoint = frozen.get("detected_viewpoint", {})
        preview = build_research_preview(observations, intervals, summary.get("observable_anatomical_side", "ambiguous"), viewpoint.get("value", "unknown"), viewpoint.get("confidence"), load_config(CONFIG))
        (analysis/"research_preview.json").write_text(json.dumps(preview, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        update(target, status="rendering_video")
        annotated = analysis / "camera_annotated.mp4"
        if annotated.exists():
            subprocess.run(["ffmpeg","-y","-i",str(annotated),"-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p","-movflags","+faststart","-an",str(target/"annotated.mp4")], check=True, capture_output=True, timeout=300)
        update(target, status="completed")
    except Exception as exc:
        update(target, status="failed", error="The analysis pipeline could not complete this recording.", internal_error=type(exc).__name__)


@app.post("/api/sessions/{session_id}/analyse", status_code=202)
def analyse(session_id: str, tasks: BackgroundTasks, request: Request) -> dict:
    target = owned_folder(request, session_id, csrf=MOBILE is not None); meta = read_meta(target)
    if meta["exercise"] != "push-up": raise HTTPException(400,"Push-up analysis is not used for pull-up recordings.")
    if not (target/"source.mp4").exists(): raise HTTPException(409,"Upload a video first.")
    if meta.get("exercise_type", "standard") != "standard":
        update(target, status="completed", message="Not assessed in this version.")
        return {"status": "completed", "assessment": "not_assessed_in_this_version"}
    update(target,status="queued"); job_id = MOBILE.create_job(session_id, mobile_user(request)["id"]) if MOBILE else None; tasks.add_task(run_analysis,target); return {"status":"queued", "job_id": job_id}


@app.get("/api/sessions/{session_id}/status")
def status(session_id: str, request: Request) -> dict: return read_meta(owned_folder(request, session_id))

@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, request: Request) -> dict:
    user = mobile_user(request); return dict(MOBILE.job(job_id, user["id"]))


@app.get("/api/sessions/{session_id}/result")
def result(session_id: str, request: Request) -> dict: return public_result(owned_folder(request, session_id))


@app.get("/api/sessions/{session_id}/review-moments")
def review_moments_for_session(session_id: str, request: Request) -> dict:
    return review_moments(owned_folder(request, session_id))


@app.get("/api/sessions/{session_id}/annotated-video")
def annotated(session_id: str, request: Request):
    source=owned_folder(request, session_id)/"annotated.mp4"
    if not source.exists(): raise HTTPException(404,"Annotated video unavailable")
    return FileResponse(source,media_type="video/mp4")


@app.get("/api/sessions/{session_id}/source-video")
def source_video(session_id: str, request: Request): return FileResponse(owned_folder(request, session_id)/"source.mp4",media_type="video/mp4")


@app.get("/api/sessions")
def sessions(request: Request, profile_id: str = "local-default") -> dict:
    if MOBILE is not None:
        user = mobile_user(request); rows=[]
        for record in MOBILE.list_workouts(user["id"]):
            try: rows.append(public_result((STORE / record["relative_path"]).resolve()))
            except Exception: rows.append({"session_id":record["id"],"status":record["status"],"created_at":record["created_at"],"exercise":record["exercise"],"error":record["error"]})
        return {"sessions": rows}
    STORE.mkdir(parents=True,exist_ok=True); rows=[]
    for target in sorted(STORE.iterdir(),key=lambda p:p.stat().st_mtime,reverse=True):
        try:
            item=public_result(target)
            if item.get("status")=="completed" and item.get("exercise")=="push-up" and item.get("profile_id", "local-default") == profile_id: rows.append(item)
        except Exception: continue
    return {"sessions":rows}


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete(session_id: str, request: Request):
    target = owned_folder(request, session_id, csrf=MOBILE is not None)
    if MOBILE:
        with MOBILE.connect() as db: db.execute("DELETE FROM workout_sessions WHERE id=? AND user_id=?", (session_id, mobile_user(request)["id"]))
    shutil.rmtree(target); return None


if WEB.is_dir():
    app.mount("/",StaticFiles(directory=WEB,html=True),name="web")
