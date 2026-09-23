# ESP32 raw sensor stream

ESP32 → Wi-Fi/LAN → ULIANA backend on laptop (port 8001) → SQLite → mobile Experimental sensor screen. The phone does not connect directly to ESP32. The readings are raw experimental signals.

## Setup

1. Install PlatformIO in the repository virtual environment with `.venv/bin/pip install platformio`. If your network requires a SOCKS proxy, also install `.venv/bin/pip install PySocks`.
2. Copy `firmware/esp32_wifi_stream/config.example.h` to `firmware/esp32_wifi_stream/config.h`.
3. In `config.h`, set the Wi-Fi SSID and password, `SERVER_URL` to `http://10.16.98.88:8001/api/sensor/ingest` (or the laptop's current LAN IP), and `DEVICE_ID`.
4. Sign in on the mobile PWA, open Experimental sensor, and create a pairing token for that device ID. Paste it into `PAIRING_TOKEN`. Tokens expire after 15 minutes and can be revoked on the screen.
5. The teammate's original C0–C15 scanner must be adapted in `src/scanner.h`. Keep its multiplexer, calibration, threshold, and serial diagnostic logic unchanged. `scannerTick()` must report a completed round and expose its 16 readings in `lastReading`. This file cannot be finalized until the original source is available.
6. Build without upload: `/home/bordch/CODE/PROJECTS/Skoltech/TEAM_10/.venv/bin/pio run -d firmware/esp32_wifi_stream`.
7. When ready, upload: `/home/bordch/CODE/PROJECTS/Skoltech/TEAM_10/.venv/bin/pio run -d firmware/esp32_wifi_stream --target upload`.
8. Open Serial Monitor at 115200 baud and check Wi-Fi, sending, error, and retry messages. Confirm `Receiving data` and raw channels on the mobile screen.

LAN HTTP is for a controlled prototype only. Restrict the endpoint to the local network. Production transport needs HTTPS.
