#!/usr/bin/env python3
"""Persistent Kokoro-82M worker for the Python 3.11 TTS environment."""
from __future__ import annotations

import base64
import contextlib
import io
import json
import sys


def main() -> None:
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    with contextlib.redirect_stdout(sys.stderr):
        pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    for line in sys.stdin:
        try:
            request = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                chunks = []
                for _, _, audio in pipeline(request["text"], voice=request["voice"]):
                    if audio is not None:
                        chunks.append(audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio))
            if not chunks:
                raise RuntimeError("Kokoro returned no audio")
            wav = io.BytesIO()
            sf.write(wav, np.concatenate(chunks), 24000, format="WAV", subtype="PCM_16")
            answer = {"wav_base64": base64.b64encode(wav.getvalue()).decode("ascii")}
        except Exception as exc:
            answer = {"error": type(exc).__name__}
        sys.stdout.write(json.dumps(answer) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
