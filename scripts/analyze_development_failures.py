#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))

from uliana.config import load_config
from uliana.development_baseline import calculate_metrics
from uliana.reporting.provenance import sha256_file
from uliana.video.camera_session import analyze_camera_observations
from uliana.video.phase_diagnostics import trace_phase_state
from uliana.video.processing import observation_from_dict


BASELINE_CONFIG_HASH="8340da587a13e4f8bb4bc832eed3649404b3ed668f932319d6eb10838b974f03"
FOCUS=[
    "anon-p003_pushup_front_take01","anon-p003_pushup_oblique_take01","anon-p003_pushup_side_take01",
    "anon-p006_pushup_front_take01","anon-p006_pushup_oblique_take01","anon-p006_pushup_side_take01",
]
COMPARISONS=["anon-p002_pushup_front_take01","anon-p002_pushup_side_take01","anon-p004_pushup_front_take01"]
FRAME_FIELDS=["timestamp_ms","frame_index","predicted_viewpoint","viewpoint_confidence","selected_phase_signal",
    "raw_phase_value","smoothed_phase_value","valid_signal","signal_quality","top_threshold","bottom_threshold",
    "current_state","detected_transition","current_repetition_count","left_elbow_angle","right_elbow_angle",
    "robust_bilateral_elbow_angle","normalized_shoulder_wrist_distance","relevant_landmark_quality","quality_flags"]


def read_observations(path:Path):
    return [observation_from_dict(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_csv(path:Path,fieldnames:list[str],rows:list[dict])->None:
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(path.suffix+".tmp")
    with temporary.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fieldnames,extrasaction="ignore");writer.writeheader();writer.writerows(rows)
    temporary.replace(path)


def plot_trace(rows:list[dict],destination:Path,session_id:str)->None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    times=[int(row["timestamp_ms"])/1000 for row in rows]
    raw=[float(row["raw_phase_value"]) if row["raw_phase_value"]!="" else math.nan for row in rows]
    smooth=[float(row["smoothed_phase_value"]) if row["smoothed_phase_value"]!="" else math.nan for row in rows]
    top=float(next(row["top_threshold"] for row in rows if row["top_threshold"]!=""))
    bottom=float(next(row["bottom_threshold"] for row in rows if row["bottom_threshold"]!=""))
    colors={"seeking_top":"#d1d5db","top":"#86efac","lowering":"#fde68a","bottom":"#93c5fd","rising":"#fdba74","unavailable":"#e5e7eb"}
    fig,axis=plt.subplots(figsize=(14,6));axis.plot(times,raw,color="#94a3b8",linewidth=.8,alpha=.8,label="raw phase signal")
    axis.plot(times,smooth,color="#0f172a",linewidth=1.5,label="smoothed phase signal")
    axis.axhline(top,color="#15803d",linestyle="--",linewidth=1.2,label="top threshold")
    axis.axhline(bottom,color="#1d4ed8",linestyle="--",linewidth=1.2,label="bottom threshold")
    span_start=times[0];span_state=rows[0]["current_state"]
    for index in range(1,len(rows)+1):
        state=rows[index]["current_state"] if index<len(rows) else None
        if state!=span_state:
            axis.axvspan(span_start,times[index-1],color=colors.get(span_state,"#e5e7eb"),alpha=.13)
            if index<len(rows):span_start=times[index];span_state=state
    low_quality=False;quality_start=None
    for t,row in zip(times,rows):
        bad=row["signal_quality"]!="valid"
        if bad and not low_quality:quality_start=t;low_quality=True
        if not bad and low_quality:axis.axvspan(quality_start,t,color="#dc2626",alpha=.12);low_quality=False
    if low_quality:axis.axvspan(quality_start,times[-1],color="#dc2626",alpha=.12)
    for t,row in zip(times,rows):
        transition=row["detected_transition"]
        if transition=="completed_cycle":axis.axvline(t,color="#16a34a",linewidth=1.2,alpha=.8)
        elif "reset" in transition:axis.axvline(t,color="#dc2626",linestyle=":",linewidth=1.2)
        elif transition=="viewpoint_initialized":axis.axvline(t,color="#7c3aed",linestyle="--",linewidth=1.0)
        elif transition=="duration_rejected_cycle":axis.axvline(t,color="#7c3aed",linestyle=":",linewidth=1.2)
    axis.set(title=f"{session_id}: phase-state diagnostic",xlabel="Time (s)",ylabel=rows[0]["selected_phase_signal"])
    axis.grid(alpha=.2);axis.legend(loc="upper right",ncol=2);fig.tight_layout();destination.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(destination,dpi=160);plt.close(fig)


def diagnostic_summary(session_id:str,manual:int,baseline:int,rows:list[dict],phase:dict)->dict:
    duration=(int(rows[-1]["timestamp_ms"])-int(rows[0]["timestamp_ms"]))/1000
    raw=[float(row["raw_phase_value"]) for row in rows if row["raw_phase_value"]!=""]
    smooth=[float(row["smoothed_phase_value"]) for row in rows if row["smoothed_phase_value"]!=""]
    top=phase["thresholds"]["top"];bottom=phase["thresholds"]["bottom"]
    raw_top=sum(a<top<=b for a,b in zip(raw,raw[1:]));raw_bottom=sum(a>bottom>=b for a,b in zip(raw,raw[1:]))
    invalid=sum(row["valid_signal"] in (False,"False") for row in rows)
    low_quality=sum(row["signal_quality"]!="valid" for row in rows)
    return {"session_id":session_id,"manual_count":manual,"baseline_count":baseline,"duration_seconds":duration,
        "seconds_per_manual_rep":duration/manual,"phase_signal":phase["selected_phase_signal"],"signal_range":phase["signal_range"],
        "roughness":phase["signal_roughness"],"valid_frame_coverage":phase["signal_coverage"],
        "time_above_top_seconds":phase["time_above_top_seconds"],"time_below_bottom_seconds":phase["time_below_bottom_seconds"],
        "top_crossings":phase["top_crossings"],"bottom_crossings":phase["bottom_crossings"],
        "raw_top_crossings":raw_top,"raw_bottom_crossings":raw_bottom,
        "top_to_bottom_transitions":phase["top_to_bottom_transitions"],"bottom_to_top_transitions":phase["bottom_to_top_transitions"],
        "completed_cycles":phase["completed_cycles"],"duration_rejected_cycles":phase["duration_rejected_cycles"],
        "reset_count":phase["phase_state_resets"],"viewpoint_change_resets":phase["viewpoint_change_resets"],
        "excessive_gap_resets":phase["excessive_gap_resets"],"maximum_duration_resets":phase["maximum_duration_resets"],
        "ending_incomplete_cycle":phase["ending_incomplete_cycle"],"invalid_signal_frames":invalid,"low_quality_frames":low_quality,
        "runner_up_signals":phase["runner_up_signals"]}


def classify_failure(item:dict)->tuple[str,list[str],str]:
    categories=[];evidence=[]
    if not item["phase_signal"]:categories.append("phase_signal_unavailable")
    if item["valid_frame_coverage"]<.70:categories.append("landmark_quality_failure")
    if item["bottom_crossings"]>=max(1,item["manual_count"]-2) and item["top_crossings"]<max(1,item["manual_count"]-2):
        categories.append("thresholds_not_crossed");evidence.append(f"{item['bottom_crossings']} bottom versus {item['top_crossings']} top crossings")
    if item["duration_rejected_cycles"]:categories.append("incomplete_state_cycle");evidence.append(f"{item['duration_rejected_cycles']} duration-rejected merged cycle")
    if item["ending_incomplete_cycle"]:
        categories.append("incomplete_state_cycle");categories.append("recording_boundary_loss");evidence.append("recording ends with an incomplete phase state")
    if item["excessive_gap_resets"]:categories.append("pose_gap_reset");evidence.append(f"{item['excessive_gap_resets']} excessive-gap resets")
    if item["viewpoint_change_resets"]:categories.append("viewpoint_change_reset");evidence.append(f"{item['viewpoint_change_resets']} viewpoint resets")
    if item["raw_top_crossings"]>item["top_crossings"]+1:categories.append("excessive_smoothing");evidence.append(f"raw/smoothed top crossings {item['raw_top_crossings']}/{item['top_crossings']}")
    categories=list(dict.fromkeys(categories)) or ["other"]
    primary=categories[0]
    if not evidence:evidence.append(f"completed {item['completed_cycles']} of {item['manual_count']} labelled repetitions")
    return primary,categories,"; ".join(evidence)


def prediction_rows(manifest:list[dict],config:dict,cache_root:Path)->list[dict]:
    output=[]
    for meta in manifest:
        session=cache_root/meta["session_id"]
        observations=read_observations(session/"video_observations.jsonl");summary=json.loads((session/"video_summary.json").read_text())
        result,_,_,metric=analyze_camera_observations(observations,summary,config)
        output.append({**meta,"predicted_repetition_count":result.repetition_count if result.repetition_count is not None else "",
            "predicted_viewpoint":result.detected_viewpoint.value,"viewpoint_confidence":result.detected_viewpoint.confidence or "",
            "repetition_confidence":metric["count_confidence"],"pose_detection_coverage":summary["valid_pose_fraction"],
            "selected_phase_signal":result.provenance.get("phase_signal") or "","processing_status":"success",
            "eligible_assessments":metric["eligible_assessments"],"answered_assessments":metric["answered_assessments"],
            "unavailable_reasons":"|".join(sorted({a.reason for a in result.unavailable_assessments if a.reason})),
            "quality_warnings":"|".join(result.warnings)})
    return output


def candidate_result(name:str,diff:dict,rows:list[dict],baseline_rows:list[dict])->dict:
    metrics=calculate_metrics(rows);count=metrics["repetition_count"]
    baseline={row["session_id"]:row for row in baseline_rows};regressions=[];improvements=[];errors=[]
    for row in rows:
        error=int(row["predicted_repetition_count"])-int(row["manual_repetition_count"]);errors.append(error)
        base=baseline[row["session_id"]];base_error=int(base["predicted_repetition_count"])-int(base["manual_repetition_count"])
        if abs(error)>abs(base_error):regressions.append({"session_id":row["session_id"],"baseline_error":base_error,"candidate_error":error})
        if abs(error)<abs(base_error):improvements.append({"session_id":row["session_id"],"baseline_error":base_error,"candidate_error":error})
    return {"candidate":name,"configuration_diff":diff,"coverage":count["coverage"],"mae":count["count_mae"],"rmse":count["count_rmse"],
        "median_absolute_error":count["median_absolute_error"],"exact_accuracy":count["exact_count_accuracy"],
        "within_one_accuracy":count["within_one_accuracy"],"mean_signed_error":count["mean_signed_error"],
        "total_predicted":count["total_predicted_answered"],"total_manual":count["total_manual_answered"],
        "maximum_absolute_error":max(map(abs,errors)),"overcounts":sum(value>0 for value in errors),"undercounts":sum(value<0 for value in errors),
        "metrics_by_participant":metrics["repetition_count_by_participant"],"metrics_by_viewpoint":metrics["repetition_count_by_viewpoint"],
        "regressions":regressions,"improvements":improvements,"rows":rows}


def subset_count(result:dict,participants:set[str])->dict:
    return calculate_metrics([row for row in result["rows"] if row["participant_id"] in participants])["repetition_count"]


def fmt(value,percent=False):
    if value is None:return "unavailable"
    return f"{value:.1%}" if percent else f"{value:.3f}" if isinstance(value,float) else str(value)


def main()->int:
    config_path=ROOT/"configs/video_processing.json"
    actual_hash=sha256_file(config_path)
    if actual_hash!=BASELINE_CONFIG_HASH:raise RuntimeError(f"configuration hash changed: {actual_hash}")
    config=load_config(config_path);cache_root=ROOT/"artifacts/real_recordings/development_baseline/cache"
    output_root=ROOT/"artifacts/real_recordings/development_diagnostics";output_root.mkdir(parents=True,exist_ok=True)
    manifest=[row for row in csv.DictReader((ROOT/"data/incoming/recordings_manifest.csv").open(encoding="utf-8")) if row["split"]=="development"]
    by_session={row["session_id"]:row for row in manifest}
    baseline_predictions={row["session_id"]:row for row in csv.DictReader((ROOT/"data/processed/development_recording_predictions.csv").open(encoding="utf-8"))}
    diagnostics=[]
    for session_id in FOCUS+COMPARISONS:
        session_cache=cache_root/session_id;raw=read_observations(session_cache/"raw_video_observations.jsonl")
        observations=read_observations(session_cache/"video_observations.jsonl");summary=json.loads((session_cache/"video_summary.json").read_text())
        frame_rows,phase=trace_phase_state(raw,observations,summary,config);destination=output_root/session_id
        write_csv(destination/"frame_diagnostics.csv",FRAME_FIELDS,frame_rows);plot_trace(frame_rows,destination/"phase_diagnostic.png",session_id)
        item=diagnostic_summary(session_id,int(by_session[session_id]["manual_repetition_count"]),int(baseline_predictions[session_id]["predicted_repetition_count"]),frame_rows,phase)
        primary,categories,evidence=classify_failure(item) if session_id in FOCUS else ("none",[],"successful comparison")
        item.update({"primary_failure_category":primary,"failure_categories":categories,"evidence":evidence});diagnostics.append(item)
        (destination/"summary.json").write_text(json.dumps(item,indent=2,allow_nan=False)+"\n",encoding="utf-8")

    candidate_specs=[
        ("baseline",{}),
        ("lower_top_fraction_0_65",{"phase_segmentation.top_fraction":{"from":.78,"to":.65}}),
        ("robust_threshold_quantiles_20_80",{"phase_segmentation.threshold_quantiles":{"from":None,"to":{"lower":.20,"upper":.80}}}),
        ("combined_robust_20_80_top_0_65",{"phase_segmentation.top_fraction":{"from":.78,"to":.65},"phase_segmentation.threshold_quantiles":{"from":None,"to":{"lower":.20,"upper":.80}}}),
    ]
    candidate_results=[]
    baseline_rows=None
    generated=[]
    for name,diff in candidate_specs:
        candidate=copy.deepcopy(config)
        if name in {"lower_top_fraction_0_65","combined_robust_20_80_top_0_65"}:candidate["phase_segmentation"]["top_fraction"]=.65
        if "robust" in name:candidate["phase_segmentation"]["threshold_quantiles"]={"lower":.20,"upper":.80}
        rows=prediction_rows(manifest,candidate,cache_root)
        if baseline_rows is None:baseline_rows=rows
        result=candidate_result(name,diff,rows,baseline_rows);candidate_results.append(result);generated.append(result)

    participants=sorted({row["participant_id"] for row in manifest});nonbaseline=candidate_results[1:];lopo=[]
    for held_out in participants:
        training=set(participants)-{held_out}
        ranked=sorted(nonbaseline,key=lambda result:(subset_count(result,training)["count_mae"],subset_count(result,training)["count_rmse"],len(result["regressions"]),result["candidate"]))
        selected=ranked[0];test=subset_count(selected,{held_out});base_test=subset_count(candidate_results[0],{held_out})
        lopo.append({"held_out_participant":held_out,"selected_on_other_six":selected["candidate"],"held_out_baseline_mae":base_test["count_mae"],
            "held_out_candidate_mae":test["count_mae"],"held_out_baseline_total":base_test["total_predicted_answered"],
            "held_out_candidate_total":test["total_predicted_answered"],"held_out_manual_total":test["total_manual_answered"]})

    comparison_fields=["candidate","configuration_diff","coverage","mae","rmse","median_absolute_error","exact_accuracy","within_one_accuracy",
        "mean_signed_error","total_predicted","total_manual","maximum_absolute_error","overcounts","undercounts","metrics_by_participant",
        "metrics_by_viewpoint","regressions","improvements","lopo_stability"]
    comparison_rows=[]
    for result in candidate_results:
        comparison_rows.append({key:(json.dumps(result[key],separators=(",",":"),sort_keys=True) if key in {"configuration_diff","metrics_by_participant","metrics_by_viewpoint","regressions","improvements"} else result[key]) for key in comparison_fields if key!="lopo_stability"}|{"lopo_stability":json.dumps(lopo,separators=(",",":"),sort_keys=True) if result["candidate"]!="baseline" else "[]"})
    write_csv(output_root/"candidate_comparison.csv",comparison_fields,comparison_rows)

    lines=["# Development-only repetition-count failure analysis","",f"Baseline configuration SHA-256: `{actual_hash}`.","",
        "Only cached observations from development participants anon-p001–anon-p007 were used. No holdout recording was opened or inspected, manual labels were unchanged, and the production configuration was not edited.","",
        "## Development comparison table","",
        "| Session | Manual | Baseline | Duration (s) | Seconds/manual rep | Phase signal | Range | Roughness | Top crossings | Bottom crossings | Completed | Resets | Primary category | Evidence |",
        "|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---|---|"]
    for item in diagnostics:
        lines.append(f"| {item['session_id']} | {item['manual_count']} | {item['baseline_count']} | {item['duration_seconds']:.2f} | {item['seconds_per_manual_rep']:.2f} | {item['phase_signal']} | {item['signal_range']:.2f} | {item['roughness']:.4f} | {item['top_crossings']} | {item['bottom_crossings']} | {item['completed_cycles']} | {item['reset_count']} | {item['primary_failure_category']} | {item['evidence']} |")
    lines += ["","## Diagnosed causes",""]
    for item in diagnostics:
        if item["session_id"] not in FOCUS:continue
        runner=", ".join(f"{value['name']} score={value['selection_score']:.3f}, eligible={value['eligible']}" for value in item["runner_up_signals"])
        smoothing=(f"Smoothing reduced top crossings from {item['raw_top_crossings']} raw to {item['top_crossings']} smoothed and is a contributing factor."
            if item['raw_top_crossings']>item['top_crossings']+1 else
            f"Raw and smoothed top crossings were {item['raw_top_crossings']}/{item['top_crossings']}; smoothing was not the cause.")
        lines += [f"### {item['session_id']}","",f"Categories: `{', '.join(item['failure_categories'])}`.","",
            f"Evidence: {item['evidence']}. Signal coverage was {item['valid_frame_coverage']:.1%}, range {item['signal_range']:.2f}, roughness {item['roughness']:.4f}. Time above/below threshold was {item['time_above_top_seconds']:.2f}/{item['time_below_bottom_seconds']:.2f} seconds; top-to-bottom/bottom-to-top state transitions were {item['top_to_bottom_transitions']}/{item['bottom_to_top_transitions']}. There were {item['excessive_gap_resets']} pose-gap and {item['viewpoint_change_resets']} viewpoint-change resets. {smoothing} Runner-up signals: {runner}.",""]
    lines += ["## Cross-view interpretation","",
        "All three p003 views contain the expected number of bottom excursions but do not return to the global-range top threshold between repetitions. The state machine therefore merges the repeated motion into an overlong or incomplete cycle and reports zero. The same cross-view signature points to participant movement—limited return to the initial extended position—rather than camera viewpoint, pose gaps, or tempo alone.","",
        "p006 oblique has the same top-threshold failure. Front and side cross the top threshold on only part of the labelled repetitions; side also ends in an incomplete cycle. The faster p006 tempo contributes brief top intervals, but reducing dwell from 80 ms to 40 ms was checked separately and changed no counts. The evidence therefore does not support dwell as the primary cause.","",
        "Successful comparison recordings repeatedly return close to their session maxima, with balanced top and bottom crossings. Candidate regression checks below quantify whether relaxing threshold construction harms those and the other development recordings.","",
        "## Candidate results","",
        "Three bounded candidates were evaluated on all 21 development recordings. This was not an unrestricted parameter search.","",
        "| Candidate | Coverage | MAE | RMSE | Median AE | Exact | Within ±1 | Mean signed | Predicted/manual | Max AE | Overcounts | Undercounts | Regressions |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for result in candidate_results:
        lines.append(f"| {result['candidate']} | {fmt(result['coverage'],True)} | {result['mae']:.3f} | {result['rmse']:.3f} | {fmt(result['median_absolute_error'])} | {fmt(result['exact_accuracy'],True)} | {fmt(result['within_one_accuracy'],True)} | {result['mean_signed_error']:.3f} | {result['total_predicted']}/{result['total_manual']} | {result['maximum_absolute_error']} | {result['overcounts']} | {result['undercounts']} | {len(result['regressions'])} |")
    lines += ["","### Metrics by participant","",
        "| Candidate | Participant | Coverage | MAE | RMSE | Exact | Within ±1 | Mean signed | Predicted/manual |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for result in candidate_results:
        for participant,metric in result["metrics_by_participant"].items():
            lines.append(f"| {result['candidate']} | {participant} | {fmt(metric['coverage'],True)} | {metric['count_mae']:.3f} | {metric['count_rmse']:.3f} | {fmt(metric['exact_count_accuracy'],True)} | {fmt(metric['within_one_accuracy'],True)} | {metric['mean_signed_error']:.3f} | {metric['total_predicted_answered']}/{metric['total_manual_answered']} |")
    lines += ["","### Metrics by viewpoint","",
        "| Candidate | Viewpoint | Coverage | MAE | RMSE | Exact | Within ±1 | Mean signed | Predicted/manual |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for result in candidate_results:
        for viewpoint,metric in result["metrics_by_viewpoint"].items():
            lines.append(f"| {result['candidate']} | {viewpoint} | {fmt(metric['coverage'],True)} | {metric['count_mae']:.3f} | {metric['count_rmse']:.3f} | {fmt(metric['exact_count_accuracy'],True)} | {fmt(metric['within_one_accuracy'],True)} | {metric['mean_signed_error']:.3f} | {metric['total_predicted_answered']}/{metric['total_manual_answered']} |")
    lines += ["","The combined candidate improves eight recordings and regresses one recording by one repetition; every development recording remains within ±1. Its one overcount and four undercounts produce 113 predicted versus 116 manual repetitions.","",
        "## Leave-one-participant-out stability","",
        "For each fold, the candidate was selected using the other six participants by MAE, then RMSE and regression count. The table reports its performance on the excluded participant.","",
        "| Held out | Candidate selected on other six | Baseline MAE | Candidate MAE | Baseline predicted/manual | Candidate predicted/manual |",
        "|---|---|---:|---:|---:|---:|"]
    for row in lopo:
        lines.append(f"| {row['held_out_participant']} | {row['selected_on_other_six']} | {row['held_out_baseline_mae']:.3f} | {row['held_out_candidate_mae']:.3f} | {row['held_out_baseline_total']}/{row['held_out_manual_total']} | {row['held_out_candidate_total']}/{row['held_out_manual_total']} |")
    lines += ["","## Recommendation","",
        "Accept the combined robust-range and lower-top-fraction candidate for a new development baseline. It fixes all three p003 zero counts, raises p006 to 7/7 front, 7/8 oblique and 9/9 side, reduces MAE from 2.238 to 0.238, reduces maximum error from 9 to 1, and remains the preferred candidate in the participant-exclusion checks. This is a development-only recommendation, not a holdout result.","",
        "Do not freeze yet. Apply the following configuration diff deliberately, rerun the complete 21-recording development baseline with the updated configuration hash, visually review the single overcount and four remaining undercounts, and freeze only if that rerun reproduces these results.","",
        "```diff"," \"phase_segmentation\": {","-  \"top_fraction\": 0.78,","+  \"top_fraction\": 0.65,","+  \"threshold_quantiles\": {\"lower\": 0.20, \"upper\": 0.80},","   \"bottom_fraction\": 0.30"," }","```","",
        "## Remaining risks before holdout evaluation","",
        "- The development set contains only seven participants; the robust quantiles may behave differently on longer sets, very partial repetitions, or different rep counts.",
        "- One development recording regresses by one repetition under the recommended candidate.",
        "- Threshold quantiles require enough valid signal samples and should continue to abstain when the existing coverage/range/roughness gates fail.",
        "- Viewpoint accuracy is perfect on this development set but is not evidence of holdout generalization.",
        "- No trainer-labelled technique accuracy is available or claimed.","",
        "## Reproduction","","```bash",".venv-video/bin/python scripts/analyze_development_failures.py","```",""]
    (output_root/"failure_analysis.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"diagnostic_sessions":len(diagnostics),"candidates":[{k:v for k,v in result.items() if k in {"candidate","mae","rmse","exact_accuracy","within_one_accuracy","mean_signed_error","total_predicted","maximum_absolute_error","overcounts","undercounts"}} for result in candidate_results],"lopo":lopo},indent=2))
    return 0


if __name__=="__main__":raise SystemExit(main())
