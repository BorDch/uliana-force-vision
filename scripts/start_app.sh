#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

for command_name in node npm ffmpeg ffprobe lsof; do
  command -v "$command_name" >/dev/null || { echo "Missing required executable: $command_name"; exit 1; }
done

if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port 8000 is already in use. ULIANA did not stop the existing process:"
  lsof -nP -iTCP:8000 -sTCP:LISTEN
  echo "Stop that process, then run this script again."
  exit 1
fi

[ -x .venv-video/bin/python ] || { echo "Missing .venv-video. Create the Python 3.11 video environment described in README.md."; exit 1; }
.venv-video/bin/python -c 'import fastapi, uvicorn, multipart, mediapipe, cv2' 2>/dev/null || { echo "Install app dependencies: .venv-video/bin/pip install -e \".[video,demo]\""; exit 1; }
[ -f models/pose_landmarker_full.task ] || { echo "Missing MediaPipe pose model."; exit 1; }

echo "Building the shared ULIANA frontend…"
(cd uliana-demo && npm run build)

LAN_IP="$(ip -4 -o addr show scope global 2>/dev/null | awk '$2 ~ /^(wl|en|eth)/ {sub(/\/.*/,"",$4); print $4; exit}')"
echo ""
echo "ULIANA application is ready:"
echo "Local:"
echo "http://127.0.0.1:8000/"
if [ -n "$LAN_IP" ]; then
  echo "Network:"
  echo "http://$LAN_IP:8000/"
else
  echo "Network: unavailable (no LAN IPv4 address detected)"
fi
echo "Keep this terminal open. Press Ctrl-C to stop cleanly."
exec env ULIANA_MODE=app .venv-video/bin/python -m uvicorn scripts.demo_server:app --host 0.0.0.0 --port 8000
