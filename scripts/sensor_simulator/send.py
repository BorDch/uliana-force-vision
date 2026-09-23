#!/usr/bin/env python3
"""SIMULATED raw ESP32 telemetry for the local mobile pilot."""
import argparse
import json
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def main():
    parser = argparse.ArgumentParser(description="Send SIMULATED raw sensor signals")
    parser.add_argument("--server", default="http://127.0.0.1:8001")
    parser.add_argument("--token", required=True)
    parser.add_argument("--device-id", default="esp32-demo-01")
    parser.add_argument("--session-id")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--start-sequence", type=int, default=1)
    args = parser.parse_args()
    for offset in range(args.count):
        sequence = args.start_sequence + offset
        payload = {"schema_version": 1, "device_id": args.device_id, "sequence": sequence,
                   "device_time_ms": int(time.monotonic() * 1000),
                   "channels": [{"channel_id": "channel_1", "raw_value": 1800 + sequence % 30},
                                {"channel_id": "channel_2", "raw_value": 1760 + sequence % 25}]}
        if args.session_id:
            payload["workout_session_id"] = args.session_id
        request = Request(args.server.rstrip("/") + "/api/sensors/telemetry", data=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + args.token}, method="POST")
        try:
            with urlopen(request, timeout=10) as response:
                print("SIMULATED", sequence, response.status, response.read().decode())
        except HTTPError as error:
            print("SIMULATED", sequence, error.code, error.read().decode())
        time.sleep(max(0, args.interval))


if __name__ == "__main__":
    main()
