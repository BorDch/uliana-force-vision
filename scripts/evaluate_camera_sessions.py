#!/usr/bin/env python3
from __future__ import annotations

import argparse,csv,json,statistics,sys
from collections import Counter,defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from uliana.video_evaluation import match_events


def _percentile(values,p):
    ordered=sorted(values);return ordered[min(len(ordered)-1,int(p*len(ordered)))] if ordered else None


def evaluate(manifest:Path,results_root:Path,annotations_root:Path,tolerance_seconds:float=.5)->dict:
    references=list(csv.DictReader(manifest.open(encoding="utf-8")));splits=defaultdict(set)
    for row in references:splits[row["participant_id"]].add(row.get("split","unassigned"))
    leaked={participant:sorted(values) for participant,values in splits.items() if len(values-{"unassigned"})>1}
    if leaked:raise ValueError(f"participant split leakage: {leaked}")
    sessions=[];boundary={"start":[],"bottom":[],"end":[]};condition_rows=[];unavailable=Counter()
    for ref in references:
        result_path=results_root/ref["session_id"]/"session_result.json"
        if not result_path.exists():continue
        result=json.loads(result_path.read_text(encoding="utf-8"));detected=result["repetition_count"]
        expected=int(ref["expected_repetitions"]) if ref.get("expected_repetitions","").strip() else None
        annotation_dir=annotations_root/ref["participant_id"]/ref["session_id"]
        reps_path=annotation_dir/"repetitions.csv";matches=[];annotations=[]
        if reps_path.exists():
            annotations=list(csv.DictReader(reps_path.open(encoding="utf-8")))
            usable=[row for row in annotations if row.get("bottom_ms","").strip()]
            detections=result["repetition_intervals"]
            matches=match_events([int(row["bottom_ms"])/1000 for row in usable],[row["bottom_ms"]/1000 for row in detections if row["bottom_ms"] is not None],tolerance_seconds)
            for match in matches:
                a=usable[match.annotation_index];d=detections[match.detection_index]
                for name in boundary:
                    if a.get(f"{name}_ms","").strip() and d.get(f"{name}_ms") is not None:boundary[name].append(abs(int(a[f"{name}_ms"])-d[f"{name}_ms"]))
        conditions_path=annotation_dir/"conditions.csv"
        if conditions_path.exists():
            manual=list(csv.DictReader(conditions_path.open(encoding="utf-8")));pred={(a["rep_id"],a["condition"]):a for a in result["assessments"]}
            for item in manual:
                if item["label"] in ("uncertain","not_visible"):continue
                detected_item=pred.get((int(item["rep_id"]),item["condition"]));predicted=detected_item["result"] if detected_item else "unavailable"
                condition_rows.append({"condition":item["condition"],"expected":item["label"],"predicted":predicted})
        unavailable.update(a["reason"] for a in result["unavailable_assessments"])
        sessions.append({"participant_id":ref["participant_id"],"session_id":ref["session_id"],"viewpoint":ref["true_viewpoint"],
            "detected_viewpoint":result["detected_viewpoint"]["value"],
            "expected_count":expected,"detected_count":detected,"absolute_count_error":abs(detected-expected) if detected is not None and expected is not None else None,
            "exact_count":detected==expected if detected is not None and expected is not None else None,"coverage":result["overall_assessment_coverage"],
            "abstention_rate":len(result["unavailable_assessments"])/len(result["assessments"]) if result["assessments"] else 0})
    condition_metrics={}
    for condition in sorted({row["condition"] for row in condition_rows}):
        rows=[row for row in condition_rows if row["condition"]==condition];tp=sum(r["expected"]==r["predicted"]=="condition_detected" for r in rows);fp=sum(r["expected"]!="condition_detected" and r["predicted"]=="condition_detected" for r in rows);fn=sum(r["expected"]=="condition_detected" and r["predicted"]!="condition_detected" for r in rows)
        answered=[r for r in rows if r["predicted"]!="unavailable"]
        precision=tp/(tp+fp) if tp+fp else None;recall=tp/(tp+fn) if tp+fn else None
        condition_metrics[condition]={"precision":precision,"recall":recall,"f1":2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else None,
            "coverage":len(answered)/len(rows) if rows else 0,"abstention_rate":1-len(answered)/len(rows) if rows else 0,
            "selective_error":sum(r["expected"]!=r["predicted"] for r in answered)/len(answered) if answered else None}
    errors=[row["absolute_count_error"] for row in sessions if row["absolute_count_error"] is not None]
    def grouped(key):
        output={}
        for value in sorted({row[key] for row in sessions}):
            rows=[row for row in sessions if row[key]==value];available=[r["absolute_count_error"] for r in rows if r["absolute_count_error"] is not None]
            output[value]={"sessions":len(rows),"count_mae":sum(available)/len(available) if available else None,"mean_coverage":sum(r["coverage"] for r in rows)/len(rows)}
        return output
    participants=len({row["participant_id"] for row in sessions})
    return {"status":"prototype_smoke_test_not_model_validation" if participants<3 else "evaluation",
        "session_count":len(sessions),"participant_count":participants,"repetition_count_mae":sum(errors)/len(errors) if errors else None,
        "exact_count_accuracy":sum(row["exact_count"] for row in sessions if row["exact_count"] is not None)/len(errors) if errors else None,
        "boundary_error_ms":{name:{"mean":sum(v)/len(v) if v else None,"median":statistics.median(v) if v else None,"p95":_percentile(v,.95)} for name,v in boundary.items()},
        "conditions":condition_metrics,"by_viewpoint":grouped("viewpoint"),"by_participant":grouped("participant_id"),
        "unavailable_reason_counts":dict(unavailable),"sessions":sessions,"participant_split_leakage":False}


def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument("--manifest",required=True,type=Path);parser.add_argument("--results-root",required=True,type=Path);parser.add_argument("--annotations-root",required=True,type=Path);parser.add_argument("--output",type=Path);parser.add_argument("--tolerance-seconds",type=float,default=.5);args=parser.parse_args()
    try:result=evaluate(args.manifest,args.results_root,args.annotations_root,args.tolerance_seconds)
    except ValueError as exc:print(f"ERROR: {exc}",file=sys.stderr);return 1
    payload=json.dumps(result,indent=2,allow_nan=False)+"\n";print(payload,end="")
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(payload,encoding="utf-8")
    return 0


if __name__=="__main__":raise SystemExit(main())
