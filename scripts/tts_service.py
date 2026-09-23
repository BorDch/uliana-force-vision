"""Process-local bridge to the persistent Kokoro worker; no text is stored."""
from __future__ import annotations

import base64
import json
import os
import select
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_LOCK = threading.Lock()
_WORKER: subprocess.Popen[str] | None = None


def synthesize_wav(text: str, voice: str = "af_heart") -> bytes:
    global _WORKER
    with _LOCK:
        if _WORKER is None or _WORKER.poll() is not None:
            python = Path(os.environ.get("ULIANA_TTS_PYTHON", ROOT / ".venv-tts" / "bin" / "python"))
            if not python.is_file():
                raise RuntimeError("TTS Python environment is missing")
            environment = os.environ.copy()
            environment.setdefault("HF_HOME", str(ROOT / ".kokoro-cache"))
            _WORKER = subprocess.Popen([str(python), "-u", str(ROOT / "scripts" / "tts_worker.py")],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
                                       text=True, bufsize=1, env=environment)
        assert _WORKER.stdin is not None and _WORKER.stdout is not None
        try:
            _WORKER.stdin.write(json.dumps({"text": text, "voice": voice}) + "\n")
            _WORKER.stdin.flush()
            ready, _, _ = select.select([_WORKER.stdout], [], [], 120)
            if not ready:
                raise TimeoutError("TTS worker timed out")
            response = json.loads(_WORKER.stdout.readline())
            if "error" in response:
                raise RuntimeError(f"TTS worker failed: {response['error']}")
            return base64.b64decode(response["wav_base64"], validate=True)
        except Exception:
            _WORKER.kill()
            _WORKER = None
            raise
