#!/usr/bin/env python3
from __future__ import annotations

import argparse,json,sys
from dataclasses import replace
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from uliana.config import load_config
from uliana.contracts.models import CalibrationState,GridPosition,PressureObservation,SynchronizationReport
from uliana.contracts.validation import validate_contract
from uliana.fusion.aggregation import aggregate_repetition_pressure
from uliana.fusion.assessments import assess_hand_pressure_stability,assess_pressure_balance,assess_pressure_signal_quality
from uliana.fusion.cue_selection import select_primary_cues
from uliana.pressure.calibration import apply_calibration,load_calibrations
from uliana.pressure.ingestion import PressureIssue,read_pressure_csv
from uliana.pressure.quality import analyze_pressure_quality
from uliana.reporting.provenance import StaleCacheError,build_provenance,verify_cache
from uliana.reporting.replay_adapter import replay_packets
from uliana.reporting.session_report import build_session_result
from uliana.synchronization.alignment import estimate_alignment
from uliana.synchronization.diagnostics import synchronization_report
from uliana.synchronization.matching import interpolate_pressure
from uliana.video.camera_session import analyze_camera_observations,render_camera_video
from uliana.video.ingestion import VideoReader
from uliana.video.pose_estimator import MediaPipeObservationAdapter
from uliana.video.processing import observation_from_dict,process_observations,write_observations


def _read_jsonl(path:Path)->list[dict]:return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
def _write_json(path:Path,value)->None:path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n",encoding="utf-8")
def _write_jsonl(path:Path,values:list[dict])->None:path.write_text("".join(json.dumps(v,separators=(",",":"),allow_nan=False)+"\n" for v in values),encoding="utf-8")


def _pressure_from_dict(value:dict)->PressureObservation:
    grid=value.get("grid_position");cal=value.get("calibration") or {"status":"unknown"}
    return PressureObservation(value["schema_version"],value["session_id"],value["timestamp_ms"],value["timestamp_source"],
        value["sensor_id"],value["channel_id"],value["raw_value"],value.get("calibrated_force_n"),
        CalibrationState(**cal),GridPosition(**grid) if grid else None,value.get("quality_flags",[]))


def main()->int:
    parser=argparse.ArgumentParser(description="Analyze one consented push-up camera/pressure session.")
    parser.add_argument("session_dir",type=Path);parser.add_argument("--output-dir",required=True,type=Path)
    parser.add_argument("--video-config",type=Path,default=ROOT/"configs/video_processing.json")
    parser.add_argument("--pressure-config",type=Path,default=ROOT/"configs/pressure_quality.json")
    parser.add_argument("--fusion-config",type=Path,default=ROOT/"configs/fusion.json")
    parser.add_argument("--calibration",type=Path);parser.add_argument("--model",type=Path,default=ROOT/"models/pose_landmarker_full.task")
    parser.add_argument("--cached-video-observations",type=Path);parser.add_argument("--cached-video-summary",type=Path)
    parser.add_argument("--cached-pressure-observations",type=Path);parser.add_argument("--cache-manifest",type=Path)
    parser.add_argument("--force",action="store_true");parser.add_argument("--json-only",action="store_true")
    parser.add_argument("--no-annotated-video",action="store_true");parser.add_argument("--json",action="store_true")
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    metadata_path=args.session_dir/"metadata.json"
    metadata=json.loads(metadata_path.read_text(encoding="utf-8"));validate_contract("metadata",metadata)
    if metadata["consent_status"]!="granted":raise ValueError(f"session consent is {metadata['consent_status']!r}; processing refused")
    video_path=args.session_dir/"video.mp4";pressure_path=args.session_dir/"pressure.csv"
    video_config=load_config(args.video_config);pressure_config=load_config(args.pressure_config);fusion_config=load_config(args.fusion_config)
    sync_meta=metadata.get("synchronization") or {"mode":"unavailable"}
    pressure_config={**pressure_config,**{key:sync_meta[key] for key in ("expected_channels","nominal_sampling_rate_hz","regions","maximum_interpolation_gap_ms") if sync_meta.get(key) is not None}}
    cache_inputs={"metadata":metadata_path,"video":video_path if video_path.exists() else None,"pressure":pressure_path if pressure_path.exists() else None,
        "cached_video_observations":args.cached_video_observations,"cached_video_summary":args.cached_video_summary,
        "cached_pressure_observations":args.cached_pressure_observations}
    cache_configs={"video":args.video_config,"pressure":args.pressure_config,"fusion":args.fusion_config,"calibration":args.calibration}
    effective_model=args.model if video_path.exists() and not args.cached_video_observations else None
    if args.cache_manifest and not args.force:verify_cache(args.cache_manifest,inputs=cache_inputs,configs=cache_configs,model=effective_model)
    warnings=[];limitations=["prototype_not_medical_device","monocular_camera_not_validated_3d_or_360_motion_capture"]
    camera_result=None;observations=[];video_summary=None;phases={};camera_features=[]
    if video_path.exists() or args.cached_video_observations:
        try:
            if args.cached_video_observations:
                observations=[observation_from_dict(v) for v in _read_jsonl(args.cached_video_observations)]
                if any(item.session_id!=metadata["session_id"] for item in observations):
                    raise ValueError("cached video observation session_id/source mismatch")
                if args.cached_video_summary:video_summary=json.loads(args.cached_video_summary.read_text(encoding="utf-8"))
                else:observations,video_summary=process_observations(observations,video_config)
            else:
                raw=[item for item,_ in MediaPipeObservationAdapter(args.model).process(video_path,metadata["session_id"])]
                observations,video_summary=process_observations(raw,video_config)
            camera_result,camera_features,phases,_=analyze_camera_observations(observations,video_summary,video_config)
            write_observations(args.output_dir/"video_observations.jsonl",observations)
            _write_json(args.output_dir/"video_summary.json",video_summary);_write_json(args.output_dir/"camera_repetition_features.json",camera_features)
        except Exception as exc:
            warnings.append(f"camera_processing_failed:{type(exc).__name__}:{exc}");limitations.append("camera_modality_unavailable")
    else:warnings.append("video_absent");limitations.append("camera_modality_unavailable")
    pressure=[];pressure_issues:list[PressureIssue]=[]
    if args.cached_pressure_observations:
        pressure=[_pressure_from_dict(v) for v in _read_jsonl(args.cached_pressure_observations)]
        if any(item.session_id!=metadata["session_id"] for item in pressure):raise ValueError("cached pressure observation session_id/source mismatch")
    elif pressure_path.exists():
        ingested=read_pressure_csv(pressure_path,metadata["session_id"]);pressure=ingested.observations;pressure_issues+=ingested.issues
    else:warnings.append("pressure_stream_absent");limitations.append("pressure_modality_unavailable")
    calibration_id=None
    if pressure and args.calibration:
        calibrations,issues=load_calibrations(args.calibration);pressure_issues+=issues
        calibrated=apply_calibration(pressure,calibrations);pressure=calibrated.observations;pressure_issues+=calibrated.issues
        ids={item.calibration.calibration_id for item in pressure if item.calibration.calibration_id};calibration_id=",".join(sorted(ids)) or None
    diagnostics=analyze_pressure_quality(pressure,pressure_config,pressure_issues)
    if pressure:_write_jsonl(args.output_dir/"pressure_observations.jsonl",[item.to_dict() for item in pressure])
    _write_json(args.output_dir/"pressure_diagnostics.json",diagnostics.to_dict())
    alignment=estimate_alignment(sync_meta.get("mode","unavailable"),sync_meta.get("configured_offset_ms"),sync_meta.get("anchors"))
    aligned=[];matching={}
    if camera_result and pressure:
        _,matching=interpolate_pressure([o.timestamp_ms for o in observations],pressure,alignment,pressure_config.get("maximum_interpolation_gap_ms",100))
        sync_report=synchronization_report(alignment,matching,fusion_config["minimum_pressure_coverage"])
        aligned=[replace(item,timestamp_ms=round(alignment.pressure_to_video_ms(item.timestamp_ms))) for item in pressure] if alignment.available else []
    elif camera_result:sync_report=SynchronizationReport("not_applicable",reason="camera_only_session")
    else:sync_report=SynchronizationReport("unavailable",method=alignment.method,reason="video_clock_unavailable")
    synchronized=[]
    if observations:
        frames,_=interpolate_pressure([o.timestamp_ms for o in observations],pressure,alignment,pressure_config.get("maximum_interpolation_gap_ms",100))
        synchronized=[{"timestamp_ms":f.video_timestamp_ms,"channels":f.channels} for f in frames]
    _write_jsonl(args.output_dir/"synchronized_observations.jsonl",synchronized)
    aggregations=[];pressure_assessments=[];critical_all=sorted({i.code for i in diagnostics.issues if i.code in fusion_config["critical_quality_codes"]})
    expected_count=len(pressure_config.get("expected_channels") or {p.channel_id for p in pressure})
    if camera_result and pressure:
        for interval in camera_result.repetition_intervals:
            agg=aggregate_repetition_pressure(interval,aligned,fusion_config,pressure_config);aggregations.append(agg.to_dict())
            pressure_assessments.extend((assess_pressure_balance(agg,sync_report.status,expected_count,critical_all,fusion_config),
                assess_hand_pressure_stability(agg,sync_report.status,expected_count,critical_all,fusion_config),
                assess_pressure_signal_quality(agg,critical_all)))
    assessments=(camera_result.assessments if camera_result else [])+pressure_assessments
    cues,cue_warnings=select_primary_cues(assessments,fusion_config);warnings+=cue_warnings
    counts={condition:sum(a.condition==condition and a.result=="condition_detected" for a in assessments) for condition in fusion_config["cue_priority"]}
    repeated=[condition for condition,count in counts.items() if count>=fusion_config["repeat_condition_minimum_repetitions"]]
    session_cue=next((cues[r] for r in sorted(cues) if cues[r]["condition"] in repeated),None)
    cue_bundle={"per_repetition":list(cues.values()),"session":session_cue}
    mode="multimodal" if camera_result and pressure else "camera_only" if camera_result else "pressure_only"
    declaration="real_camera_simulated_pressure" if camera_result and pressure and metadata.get("test_fixture") else "real_camera_real_pressure" if camera_result and pressure else "real_camera_only" if camera_result else "pressure_diagnostic_only"
    video_info=VideoReader(video_path).metadata().__dict__ if video_path.exists() else None
    provenance=build_provenance(inputs=cache_inputs,configs=cache_configs,model=effective_model if effective_model and effective_model.exists() else None,
        calibration_id=calibration_id,synchronization_method=sync_report.method,data_declaration=declaration,
        source_video=video_info,pressure_source="cached_replay" if args.cached_pressure_observations else "canonical_csv" if pressure_path.exists() else None)
    provenance["participant_id"]=metadata["participant_id"]
    result=build_session_result(session_id=metadata["session_id"],mode=mode,camera_result=camera_result,
        pressure_assessments=pressure_assessments,pressure_aggregations=aggregations,synchronization=sync_report,
        pressure_available=bool(pressure),primary_cue=cue_bundle,repeated_conditions=repeated,warnings=warnings,
        limitations=limitations,provenance=provenance)
    validate_contract("session_result",result);_write_json(args.output_dir/"session_result.json",result.to_dict())
    _write_json(args.output_dir/"provenance.json",provenance);_write_jsonl(args.output_dir/"dashboard_replay.jsonl",replay_packets(result))
    annotation_path=args.session_dir/"annotations.json"
    if annotation_path.exists():
        reference=json.loads(annotation_path.read_text(encoding="utf-8"));expected=reference.get("repetition_count")
        evaluation={"status":"evaluation_with_manual_references","session_id":result.session_id,
            "repetition_count_error":abs(result.repetition_count-expected) if expected is not None and result.repetition_count is not None else None,
            "exact_count":result.repetition_count==expected if expected is not None and result.repetition_count is not None else None,
            "assessment_coverage":result.overall_assessment_coverage,
            "synchronization_residual_p95_ms":result.synchronization.p95_error_ms,
            "note":"No multimodal improvement claim is made from a single session."}
        _write_json(args.output_dir/"evaluation.json",evaluation)
    annotated=None
    if camera_result and video_path.exists() and not args.no_annotated_video and not args.json_only:
        annotated=args.output_dir/"annotated.mp4";render_camera_video(video_path,annotated,observations,result,phases)
    payload={"session_id":result.session_id,"mode":mode,"repetition_count":result.repetition_count,"coverage":result.coverage,
        "synchronization":result.synchronization.to_dict(),"primary_cue":result.primary_cue,"data_declaration":declaration,
        "session_result":str(args.output_dir/"session_result.json"),"annotated_video":str(annotated) if annotated else None}
    print(json.dumps(payload,indent=2) if args.json else f"Session {result.session_id}: {mode}, repetitions={result.repetition_count}, report={payload['session_result']}")
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except (ValueError,StaleCacheError) as exc:print(f"ERROR: {exc}",file=sys.stderr);raise SystemExit(2)
