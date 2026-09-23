#!/usr/bin/env python3
"""Deterministic SIMULATED sixteen-channel raw telemetry."""
import argparse
import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def make_payload(device_id, sequence, session_id=None):
    payload = {"schema_version": 1, "device_id": device_id, "sequence": sequence,
               "device_time_ms": sequence * 250,
               "channels": [{"channel_id": f"channel_{i}", "raw_value": 1700 + i * 7 + ((sequence * 13 + i * 3) % 41)} for i in range(16)]}
    if session_id:
        payload["workout_session_id"] = session_id
    return payload


def main():
    parser = argparse.ArgumentParser(description="SIMULATED raw sensor stream")
    parser.add_argument("--server", default="http://127.0.0.1:8001")
    parser.add_argument("--token", required=True)
    parser.add_argument("--device-id", default="esp32-demo-01")
    parser.add_argument("--session-id")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--drop-sequence", type=int)
    parser.add_argument("--malformed", action="store_true")
    args = parser.parse_args()
    if args.count < 0 or args.interval < 0: parser.error("count and interval must be nonnegative")
    sequence = 1
    for index in range(args.count):
        if sequence == args.drop_sequence: sequence += 1
        payload = make_payload(args.device_id, sequence, args.session_id)
        body = b'{bad json' if args.malformed else json.dumps(payload).encode()
        request = Request(args.server.rstrip('/') + '/api/sensor/ingest', data=body,
                          headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + args.token}, method='POST')
        try:
            with urlopen(request, timeout=10) as response:
                print('SIMULATED', sequence, response.status, response.read().decode())
        except HTTPError as error:
            print('SIMULATED', sequence, error.code, error.read().decode())
        sequence += 1
        if index + 1 < args.count: time.sleep(args.interval)


if __name__ == '__main__': main()
