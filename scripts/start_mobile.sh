#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PORT="${ULIANA_MOBILE_PORT:-8001}"
DATA_DIR="${ULIANA_MOBILE_DATA_DIR:-$ROOT_DIR/data/mobile_pilot}"
WEB_DIR="${ULIANA_MOBILE_WEB_DIR:-$ROOT_DIR/uliana-demo/dist-mobile/client}"
PROFILE_ID="${ULIANA_MOBILE_PROFILE_ID:-mobile-owner}"
AUTH_DB="${ULIANA_AUTH_DB:-$DATA_DIR/mobile.sqlite3}"

[[ "$PORT" =~ ^[0-9]+$ ]] && (( PORT >= 1 && PORT <= 65535 )) || { echo "ULIANA_MOBILE_PORT must be a port from 1 to 65535."; exit 1; }
for command_name in node npm ffmpeg ffprobe lsof; do
  command -v "$command_name" >/dev/null || { echo "Missing required executable: $command_name"; exit 1; }
done
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use. No process was stopped:"
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN
  exit 1
fi
[ -x .venv-video/bin/python ] || { echo "Missing .venv-video. See README.md."; exit 1; }
.venv-video/bin/python -c 'import fastapi, uvicorn, multipart, mediapipe, cv2' 2>/dev/null || { echo 'Install dependencies: .venv-video/bin/pip install -e ".[video,demo]"'; exit 1; }
[ -f models/pose_landmarker_full.task ] || { echo "Missing MediaPipe pose model."; exit 1; }
if [ ! -x "${ULIANA_TTS_PYTHON:-$ROOT_DIR/.venv-tts/bin/python}" ]; then
  echo "Kokoro TTS is unavailable. Install the optional .venv-tts environment; audio review will show 'Audio unavailable' until then."
fi

echo "Building the isolated mobile frontend…"
"$ROOT_DIR/scripts/build_mobile_frontend.sh"
[ -d "$WEB_DIR" ] || { echo "Mobile build was not created at $WEB_DIR"; exit 1; }
mkdir -p "$DATA_DIR"
[ -n "${ULIANA_PILOT_CODE:-}" ] || { echo "Set ULIANA_PILOT_CODE before starting the multi-user mobile pilot."; exit 1; }

echo "ULIANA mobile is ready at http://127.0.0.1:$PORT/"
echo "For phone access over HTTPS, run in another terminal: ngrok http $PORT"
echo "Runtime data: $DATA_DIR"
exec env ULIANA_MODE=mobile ULIANA_PROFILE_ID="$PROFILE_ID" ULIANA_DATA_DIR="$DATA_DIR" ULIANA_WEB_DIR="$WEB_DIR" ULIANA_AUTH_DB="$AUTH_DB" \
  .venv-video/bin/python -m uvicorn scripts.demo_server:app --host 0.0.0.0 --port "$PORT"
