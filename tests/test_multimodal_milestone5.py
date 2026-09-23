from __future__ import annotations

import csv,json,math,subprocess,sys
from pathlib import Path

import pytest

from uliana.contracts.models import (AssessmentResult,CalibrationState,GridPosition,PressureObservation,
                                     RepetitionInterval,SessionResult,SynchronizationReport,ViewpointEstimate)
from uliana.contracts.validation import validate_contract
from uliana.fusion.aggregation import aggregate_repetition_pressure
from uliana.fusion.assessments import assess_hand_pressure_stability,assess_pressure_balance
from uliana.fusion.cue_selection import select_primary_cues
from uliana.reporting.provenance import StaleCacheError,build_provenance,verify_cache
from uliana.reporting.replay_adapter import replay_packets


def configs():
    root=Path(__file__).parents[1]
    return (json.loads((root/"configs/fusion.json").read_text()),json.loads((root/"configs/pressure_quality.json").read_text()))


def observations(calibrated=True,imbalance=True,flags=()):
    output=[]
    for timestamp in range(0,1001,100):
        for channel,column in (("left",0),("right",1)):
            force=(80 if channel=="left" and imbalance else 50)
            output.append(PressureObservation("1.0","s",timestamp,"relative","mat",channel,force,
                force if calibrated else None,CalibrationState("calibrated" if calibrated else "uncalibrated"),
                GridPosition(0,column),list(flags)))
    return output


def test_valid_aggregation_impulse_regions_and_cop_are_interval_bounded():
    fusion,pressure=configs();pressure.update({"expected_channels":["left","right"],"nominal_sampling_rate_hz":10,
        "regions":{"left_palm":["left"],"right_palm":["right"]}})
    values=observations()+[PressureObservation("1.0","s",1500,"relative","mat","left",999,999,CalibrationState("calibrated"),GridPosition(0,0),[])]
    agg=aggregate_repetition_pressure(RepetitionInterval(1,0,500,1000,.9),values,fusion,pressure)
    assert agg.sample_count==22 and agg.total_impulse_ns==pytest.approx(130)
    assert agg.maximum_total_force_n==130 and agg.imbalance_persistence_fraction>.5
    assert len(agg.centre_of_pressure_trajectory)==11
    assessment=assess_pressure_balance(agg,"acceptable",2,[],fusion)
    assert assessment.result=="condition_detected"


@pytest.mark.parametrize("status,critical,reason",[("unavailable",[],"synchronization_unavailable_or_poor"),("poor",[],"synchronization_unavailable_or_poor"),("acceptable",["stuck_signal"],"critical_pressure_quality_issue"),("acceptable",["saturated_raw_value"],"critical_pressure_quality_issue")])
def test_pressure_gates_abstain(status,critical,reason):
    fusion,pressure=configs();pressure.update({"expected_channels":["left","right"],"nominal_sampling_rate_hz":10,"regions":{"left_palm":["left"],"right_palm":["right"]}})
    agg=aggregate_repetition_pressure(RepetitionInterval(1,0,500,1000,.9),observations(),fusion,pressure)
    assert assess_pressure_balance(agg,status,2,critical,fusion).reason==reason


def test_uncalibrated_and_missing_region_abstain_without_physical_values():
    fusion,pressure=configs();pressure.update({"expected_channels":["left","right"],"nominal_sampling_rate_hz":10})
    agg=aggregate_repetition_pressure(RepetitionInterval(1,0,500,1000,.9),observations(False),fusion,pressure)
    assert agg.total_impulse_ns is None and agg.raw_only_features["label"]=="non_physical_raw_signal"
    assert assess_pressure_balance(agg,"acceptable",2,[],fusion).reason=="pressure_calibration_unavailable"
    calibrated=aggregate_repetition_pressure(RepetitionInterval(1,0,500,1000,.9),observations(),fusion,pressure)
    assert assess_pressure_balance(calibrated,"acceptable",2,[],fusion).reason=="required_pressure_region_missing"


def test_stability_requires_trainer_threshold_and_grid():
    fusion,pressure=configs();pressure.update({"expected_channels":["left","right"],"nominal_sampling_rate_hz":10})
    agg=aggregate_repetition_pressure(RepetitionInterval(1,0,500,1000,.9),observations(),fusion,pressure)
    assert assess_hand_pressure_stability(agg,"acceptable",2,[],fusion).reason=="trainer_threshold_not_configured"


def test_single_cue_conflict_and_unavailable_suppression():
    fusion,_=configs();rows=[AssessmentResult("body_alignment_deviation","condition_detected",.8,rep_id=1,modality="camera"),
        AssessmentResult("body_alignment_deviation","adequate",.9,rep_id=1,modality="camera"),
        AssessmentResult("push_up_depth_proxy","condition_detected",.8,rep_id=1,modality="camera"),
        AssessmentResult("left_right_pressure_balance","unavailable",None,"no_sync",1,"pressure")]
    cues,warnings=select_primary_cues(rows,fusion)
    assert cues[1]["condition"]=="push_up_depth_proxy" and len(cues)==1
    assert warnings==["conflicting_evidence:body_alignment_deviation:rep_1"]


def test_cache_hash_mismatch_is_rejected(tmp_path):
    source=tmp_path/"source";config=tmp_path/"config";source.write_text("a");config.write_text("c")
    provenance=build_provenance(inputs={"source":source},configs={"config":config},model=None,calibration_id=None,
        synchronization_method=None,data_declaration="synthetic")
    manifest=tmp_path/"manifest.json";manifest.write_text(json.dumps(provenance));source.write_text("b")
    with pytest.raises(StaleCacheError,match="source hash mismatch"):verify_cache(manifest,inputs={"source":source},configs={"config":config},model=None)


def test_cache_configuration_mismatch_is_rejected(tmp_path):
    source=tmp_path/"source";config=tmp_path/"config";source.write_text("a");config.write_text("c")
    provenance=build_provenance(inputs={"source":source},configs={"config":config},model=None,calibration_id=None,
        synchronization_method=None,data_declaration="synthetic")
    manifest=tmp_path/"manifest.json";manifest.write_text(json.dumps(provenance));config.write_text("changed")
    with pytest.raises(StaleCacheError,match="configuration hash mismatch"):verify_cache(manifest,inputs={"source":source},configs={"config":config},model=None)


def test_schema_valid_multimodal_result_and_replay_omits_force():
    result=SessionResult("1.0","s","multimodal",1,[RepetitionInterval(1,0,500,1000,.8)],ViewpointEstimate("side",.8),[],None,
        SynchronizationReport("acceptable",matched_fraction=1),0,provenance={},repetition_results=[{"rep_id":1}],
        modality_availability={"camera":True,"pressure":False},coverage={"camera":0,"pressure":0,"synchronized":1,"assessment":0,"abstention":0})
    validate_contract("session_result",result)
    packet=replay_packets(result)[0]
    assert "mean_total_force_n" not in packet["measurements"] and "force" in packet["unavailable"]


def test_complete_cli_smoke(tmp_path):
    root=Path(__file__).parents[1];session=tmp_path/"session";output=tmp_path/"report";session.mkdir()
    metadata={"schema_version":"1.0","participant_id":"fixture","session_id":"cli-smoke","experience_level":"unknown",
        "camera_viewpoint":"side","exercise_variation":"push_up","expected_repetitions":1,"intentionally_performed_condition":None,
        "consent_status":"granted","hardware_configuration":{"pressure_sensor_id":"mat"},"notes":"deterministic fixture",
        "test_fixture":True,"synchronization":{"mode":"shared_relative_clock","expected_channels":["left","right"],
        "nominal_sampling_rate_hz":20,"regions":{"left_palm":["left"],"right_palm":["right"]},"maximum_interpolation_gap_ms":100}}
    (session/"metadata.json").write_text(json.dumps(metadata))
    cached=tmp_path/"video.jsonl";summary=tmp_path/"summary.json"
    angles=[165,165,165,145,145,125,95,95,95,125,125,145,165,165,165,165,165]
    values=[]
    for index,angle in enumerate(angles):
        elbow=(.55,.45);wrist=(.72,.45);theta=math.radians(angle);shoulder=(elbow[0]+.18*math.cos(theta),elbow[1]+.18*math.sin(theta));ankle=(.12,.62);hip=((shoulder[0]+ankle[0])/2,(shoulder[1]+ankle[1])/2)
        landmarks={}
        for side,shift in (("left",0),("right",.02)):
            for name,point in (("shoulder",shoulder),("elbow",elbow),("wrist",wrist),("hip",hip),("ankle",ankle)):
                landmarks[f"{side}_{name}"]={"x":point[0]+shift,"y":point[1],"z":0,"visibility":1,"presence":1}
        values.append({"schema_version":"1.0","session_id":"cli-smoke","frame_index":index,"timestamp_ms":index*50,"timestamp_source":"fixture","fps":20,
            "image_width_px":100,"image_height_px":100,"pose":{"detected":True,"landmarks":landmarks,"model_confidence":.9,"raw_landmarks":landmarks,"world_landmarks":None,"world_landmarks_caveat":None},
            "viewpoint":{"value":"side","confidence":.9,"reason":"fixture"},"quality_flags":[]})
    cached.write_text("".join(json.dumps(v)+"\n" for v in values));summary.write_text(json.dumps({"dominant_viewpoint":{"value":"side","confidence":.9,"reason":"fixture"},"observable_anatomical_side":"left","viewpoint_changes":[],"warnings":[]}))
    columns=["timestamp_ms","timestamp_source","sensor_id","channel_id","row","column","raw_value","calibrated_force_n","calibration_status","quality_flags"]
    with (session/"pressure.csv").open("w",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=columns);writer.writeheader()
        for timestamp in range(0,801,50):
            for channel,column,force in (("left",0,80),("right",1,50)):
                writer.writerow(dict(timestamp_ms=timestamp,timestamp_source="fixture",sensor_id="mat",channel_id=channel,row=0,column=column,raw_value=force,calibrated_force_n=force,calibration_status="calibrated",quality_flags=""))
    command=[sys.executable,str(root/"scripts/analyze_session.py"),str(session),"--output-dir",str(output),
        "--cached-video-observations",str(cached),"--cached-video-summary",str(summary),"--json-only","--json"]
    completed=subprocess.run(command,cwd=root,capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr
    result=json.loads((output/"session_result.json").read_text());validate_contract("session_result",result)
    assert result["mode"]=="multimodal" and result["repetition_count"]==1
    assert result["provenance"]["data_declaration"]=="real_camera_simulated_pressure"
    assert (output/"dashboard_replay.jsonl").exists() and (output/"synchronized_observations.jsonl").exists()
