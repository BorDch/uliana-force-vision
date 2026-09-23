#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$ROOT_DIR/uliana-demo"
ACTIVE="$FRONTEND/dist"
MOBILE="$FRONTEND/dist-mobile"
TEMP_DIR="$(mktemp -d "$FRONTEND/.mobile-build.XXXXXX")"
SAVED="$TEMP_DIR/existing-dist"
NEW="$TEMP_DIR/new-mobile-dist"

restore() {
  if [ -d "$ACTIVE" ] && [ ! -d "$NEW" ]; then mv "$ACTIVE" "$NEW"; fi
  if [ -d "$SAVED" ]; then mv "$SAVED" "$ACTIVE"; fi
}
trap restore EXIT INT TERM

if [ -d "$ACTIVE" ]; then mv "$ACTIVE" "$SAVED"; fi
(cd "$FRONTEND" && npm run build)
mv "$ACTIVE" "$NEW"
if [ -d "$MOBILE" ]; then mv "$MOBILE" "$TEMP_DIR/previous-mobile"; fi
mv "$NEW" "$MOBILE"
# The mobile router reads ?screen=live on /app; export only prerenders /.
# Serve the same client shell at /app without changing backend routes.
mkdir -p "$MOBILE/client/app"
cp "$MOBILE/client/index.html" "$MOBILE/client/app/index.html"
cp "$MOBILE/client/index.rsc" "$MOBILE/client/app/index.rsc"
restore
trap - EXIT INT TERM
rm -rf "$TEMP_DIR"
echo "Mobile frontend built at $MOBILE without replacing $ACTIVE"
