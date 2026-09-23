#!/usr/bin/env python3
"""Generate deterministic, explicitly simulated two-channel pressure for integration tests."""
from __future__ import annotations

import argparse,csv,math
from pathlib import Path


def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument("output",type=Path);parser.add_argument("--duration-ms",type=int,required=True)
    parser.add_argument("--sampling-rate-hz",type=float,default=30);parser.add_argument("--period-ms",type=float,default=1000)
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True);step=1000/args.sampling_rate_hz
    columns=["timestamp_ms","timestamp_source","sensor_id","channel_id","row","column","raw_value","calibrated_force_n","calibration_status","quality_flags"]
    with args.output.open("w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=columns);writer.writeheader();index=0
        while round(index*step)<=args.duration_ms:
            timestamp=round(index*step);wave=.5-.5*math.cos(2*math.pi*timestamp/args.period_ms)
            for channel,column,bias in (("left",0,1.05),("right",1,.95)):
                force=(45+35*wave)*bias
                writer.writerow({"timestamp_ms":timestamp,"timestamp_source":"simulated_shared_relative_clock","sensor_id":"simulated_two_channel_mat",
                    "channel_id":channel,"row":0,"column":column,"raw_value":f"{force:.6f}","calibrated_force_n":f"{force:.6f}",
                    "calibration_status":"calibrated","quality_flags":"simulated_fixture"})
            index+=1
    print(f"SIMULATED pressure fixture: {args.output}");return 0


if __name__=="__main__":raise SystemExit(main())
