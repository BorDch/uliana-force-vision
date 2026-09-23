#!/usr/bin/env python3
from __future__ import annotations

import argparse,csv,json,statistics,sys
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))


def main()->int:
    parser=argparse.ArgumentParser(description="Evaluate unified session reports without overstating unlabelled smoke tests.")
    parser.add_argument("reports",type=Path);parser.add_argument("--annotations",type=Path);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();results=[json.loads(p.read_text(encoding="utf-8")) for p in args.reports.rglob("session_result.json")]
    annotations={}
    if args.annotations and args.annotations.exists():
        with args.annotations.open(encoding="utf-8",newline="") as handle:
            for row in csv.DictReader(handle):annotations[row.get("session_id") or row.get("video_id")]=row
    labelled=[]
    for result in results:
        reference=annotations.get(result["session_id"])
        expected=(reference or {}).get("expected_repetitions") or (reference or {}).get("repetition_count")
        if expected not in (None,"") and result["repetition_count"] is not None:
            labelled.append(abs(result["repetition_count"]-int(expected)))
    by_view=defaultdict(list);by_participant=defaultdict(list);condition_pairs=defaultdict(list)
    for result in results:
        by_view[result["detected_viewpoint"]["value"]].append(result)
        by_participant[result.get("provenance",{}).get("participant_id","unknown")].append(result)
        reference=annotations.get(result["session_id"],{})
        for assessment in result["assessments"]:
            expected=reference.get(assessment["condition"])
            if expected in ("adequate","condition_detected") and assessment["result"]!="unavailable":
                condition_pairs[assessment["condition"]].append((expected,assessment["result"]))
    condition_metrics={}
    for condition,pairs in condition_pairs.items():
        tp=sum(a=="condition_detected" and b==a for a,b in pairs);fp=sum(a=="adequate" and b=="condition_detected" for a,b in pairs);fn=sum(a=="condition_detected" and b=="adequate" for a,b in pairs)
        precision=tp/(tp+fp) if tp+fp else None;recall=tp/(tp+fn) if tp+fn else None
        condition_metrics[condition]={"precision":precision,"recall":recall,"f1":2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else None,"labelled_assessments":len(pairs)}
    residuals=[r["synchronization"].get("p95_error_ms") for r in results if r["synchronization"].get("p95_error_ms") is not None]
    payload={"status":"evaluation_with_manual_references" if labelled else "prototype_smoke_test_not_model_validation",
        "session_count":len(results),"labelled_count_sessions":len(labelled),
        "repetition_count_mae":statistics.fmean(labelled) if labelled else None,
        "exact_count_accuracy":sum(x==0 for x in labelled)/len(labelled) if labelled else None,
        "coverage":{"camera":statistics.fmean(r["coverage"].get("camera",0) for r in results) if results else 0,
            "pressure":statistics.fmean(r["coverage"].get("pressure",0) for r in results) if results else 0,
            "combined":statistics.fmean(r["coverage"].get("assessment",0) for r in results) if results else 0},
        "by_viewpoint":{view:{"sessions":len(rows),"assessment_coverage":statistics.fmean(r["coverage"].get("assessment",0) for r in rows)} for view,rows in by_view.items()},
        "by_participant":{participant:{"sessions":len(rows),"assessment_coverage":statistics.fmean(r["coverage"].get("assessment",0) for r in rows)} for participant,rows in by_participant.items()},
        "per_condition":condition_metrics,"mean_synchronization_p95_error_ms":statistics.fmean(residuals) if residuals else None,
        "participant_level_split_required":True,
        "fusion_accuracy_claim_supported":False,
        "note":"Complementary modalities are reported separately; improvement requires the same manually labelled sessions."}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(payload,indent=2));return 0


if __name__=="__main__":raise SystemExit(main())
