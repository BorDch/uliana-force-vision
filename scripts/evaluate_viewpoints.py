#!/usr/bin/env python3
from __future__ import annotations

import argparse,csv,json
from pathlib import Path


def main()->int:
    parser=argparse.ArgumentParser(description="Evaluate manually labelled viewpoint smoke sessions.")
    parser.add_argument("--manifest",required=True,type=Path); parser.add_argument("--results-root",required=True,type=Path)
    parser.add_argument("--output",type=Path); args=parser.parse_args()
    rows=[]
    with args.manifest.open(encoding="utf-8") as handle:
        for reference in csv.DictReader(handle):
            path=args.results_root/reference["session_id"]/"video_summary.json"
            if not path.exists(): continue
            summary=json.loads(path.read_text(encoding="utf-8")); predicted=summary["dominant_viewpoint"]["value"]
            rows.append({"participant_id":reference["participant_id"],"session_id":reference["session_id"],
                "split":reference["split"],"true_viewpoint":reference["true_viewpoint"],"predicted_viewpoint":predicted,
                "correct":predicted==reference["true_viewpoint"],"unknown":predicted=="unknown"})
    result={"status":"prototype_smoke_test_not_model_validation","sessions":rows,
        "viewpoint_accuracy":sum(row["correct"] for row in rows)/len(rows) if rows else None,
        "unknown_rate":sum(row["unknown"] for row in rows)/len(rows) if rows else None,
        "participant_count":len({row["participant_id"] for row in rows}),
        "participant_separation_note":"Only development data is included; no reported test partition is claimed."}
    payload=json.dumps(result,indent=2,allow_nan=False)+"\n"
    if args.output: args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(payload,encoding="utf-8")
    print(payload,end=""); return 0


if __name__=="__main__": raise SystemExit(main())
