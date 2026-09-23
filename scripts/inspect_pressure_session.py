#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uliana.pressure import (analyze_pressure_quality, apply_calibration, compute_pressure_features,
                             load_calibrations, read_pressure_csv)
from uliana.synchronization import estimate_alignment, synchronization_report


def inspect(session: Path, calibration_path: Path | None = None, quality_config_path: Path | None = None) -> dict:
    metadata = json.loads((session / "metadata.json").read_text(encoding="utf-8"))
    sync_config = metadata.get("synchronization") or {"mode": "unavailable"}
    quality_path = quality_config_path or ROOT / "configs" / "pressure_quality.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    for key in ("expected_channels", "nominal_sampling_rate_hz", "regions", "maximum_interpolation_gap_ms"):
        if sync_config.get(key) is not None: quality[key] = sync_config[key]
    ingestion = read_pressure_csv(session / "pressure.csv", metadata["session_id"])
    observations = ingestion.observations
    calibration_issues = []
    if calibration_path is not None:
        calibrations, calibration_issues = load_calibrations(calibration_path)
        calibrated = apply_calibration(observations, calibrations)
        observations, calibration_issues = calibrated.observations, calibration_issues + calibrated.issues
    diagnostics = analyze_pressure_quality(observations, quality, ingestion.issues + calibration_issues)
    alignment = estimate_alignment(sync_config.get("mode", "unavailable"),
                                   sync_config.get("configured_offset_ms"), sync_config.get("anchors"))
    sync = synchronization_report(alignment)
    features = compute_pressure_features(observations, quality)
    unavailable = []
    if features["region_balance"]["result"] == "unavailable": unavailable.append({"feature": "region_balance", "reason": features["region_balance"]["reason"]})
    if not observations: unavailable.append({"feature": "pressure_features", "reason": "pressure_stream_absent"})
    return {"session_id": metadata["session_id"], "channels_found": diagnostics.channels_found,
            "duration_ms": diagnostics.duration_ms, "actual_sampling_rate_hz": diagnostics.sampling_rate_hz,
            "calibration_states": {channel: sorted({item.calibration.status for item in observations if item.channel_id == channel})
                                   for channel in diagnostics.channels_found},
            "issues": [issue.__dict__ for issue in diagnostics.issues], "synchronization": sync.to_dict(),
            "features": features, "unavailable_features": unavailable}


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect canonical pressure data without classifying exercise technique.")
    parser.add_argument("session", type=Path)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--quality-config", type=Path)
    parser.add_argument("--json", nargs="?", const="-", dest="json_output", help="Write JSON to a path, or stdout when omitted.")
    args = parser.parse_args()
    try:
        result = inspect(args.session, args.calibration, args.quality_config)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"ERROR: pressure inspection failed: {exc}", file=sys.stderr); return 1
    if args.json_output:
        payload = json.dumps(result, indent=2, allow_nan=False) + "\n"
        if args.json_output == "-": print(payload, end="")
        else: Path(args.json_output).write_text(payload, encoding="utf-8")
    else:
        print(f"Session: {result['session_id']}")
        print(f"Channels: {', '.join(result['channels_found']) or 'none'}")
        print(f"Duration: {result['duration_ms']} ms")
        for channel, rate in result["actual_sampling_rate_hz"].items(): print(f"Sampling rate {channel}: {rate if rate is not None else 'unavailable'} Hz")
        for issue in result["issues"]: print(f"{issue['severity'].upper()}: {issue['code']}: {issue['message']}")
        print(f"Synchronization: {result['synchronization']['status']} ({result['synchronization']['method']})")
        balance = result["features"]["region_balance"]
        print(f"Region balance: {balance['result']}" + (f" ({balance['reason']})" if balance['result'] == "unavailable" else f", {balance['imbalance_percent']:.3f}%"))
    return 1 if any(issue["severity"] == "error" for issue in result["issues"]) else 0


if __name__ == "__main__": raise SystemExit(main())
