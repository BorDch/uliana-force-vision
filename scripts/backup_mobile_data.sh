#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${ULIANA_MOBILE_DATA_DIR:-$ROOT_DIR/data/mobile_pilot}"
DB_PATH="${ULIANA_AUTH_DB:-$DATA_DIR/mobile.sqlite3}"
BACKUP_DIR="${ULIANA_BACKUP_DIR:-$ROOT_DIR/data/mobile_backups}"
RETENTION_DAYS="${ULIANA_BACKUP_RETENTION_DAYS:-14}"
INCLUDE_VIDEO="${ULIANA_BACKUP_INCLUDE_VIDEO:-0}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/$STAMP"

case "$(realpath -m "$BACKUP_DIR")" in /|"$HOME") echo "Refusing unsafe ULIANA_BACKUP_DIR: $BACKUP_DIR"; exit 1;; esac

[ -f "$DB_PATH" ] || { echo "Authentication database not found: $DB_PATH"; exit 1; }
mkdir -p "$DEST"
.venv-video/bin/python -c 'import sqlite3,sys; source=sqlite3.connect(sys.argv[1]); target=sqlite3.connect(sys.argv[2]); source.backup(target); target.execute("PRAGMA integrity_check").fetchone()[0] == "ok" or sys.exit("Backup integrity check failed"); target.close(); source.close()' "$DB_PATH" "$DEST/mobile.sqlite3"
tar --exclude='*.mp4' --exclude='*.mov' --exclude='*.m4v' --exclude='*.webm' --exclude='*.jsonl' -czf "$DEST/session-data.tar.gz" -C "$DATA_DIR" users

if [ "$INCLUDE_VIDEO" = "1" ]; then
  required_kb="$(du -sk "$DATA_DIR/users" | awk '{print $1}')"
  available_kb="$(df -Pk "$BACKUP_DIR" | awk 'NR==2 {print $4}')"
  echo "Video-inclusive backup requires approximately $((required_kb / 1024)) MiB; $((available_kb / 1024)) MiB is available."
  (( available_kb > required_kb + 102400 )) || { echo "Not enough free space for a safe video backup."; exit 1; }
  tar -czf "$DEST/user-files-with-video.tar.gz" -C "$DATA_DIR" users
else
  video_kb="$(find "$DATA_DIR/users" -type f \( -name '*.mp4' -o -name '*.mov' -o -name '*.m4v' -o -name '*.webm' \) -print0 | du --files0-from=- -ck 2>/dev/null | tail -1 | awk '{print $1+0}')"
  echo "Videos were not copied ($((video_kb / 1024)) MiB). Set ULIANA_BACKUP_INCLUDE_VIDEO=1 for an explicit video backup."
fi

.venv-video/bin/python -c 'import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"; print("SQLite backup verified")' "$DEST/mobile.sqlite3"
find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime "+$RETENTION_DAYS" -print -exec rm -rf -- {} +
echo "Backup completed: $DEST"
