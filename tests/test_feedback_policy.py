from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from uliana.reporting.feedback_policy import ASSESSMENT_POLICY, FEEDBACK_POLICY, compose_feedback, state_label

ROOT = Path(__file__).resolve().parents[1]


def assessment(condition="body_alignment_deviation", result="adequate", rep_id=1, reason=None, evidence=None):
    return {"condition": condition, "result": result, "confidence": .8 if result != "unavailable" else None,
            "reason": reason, "rep_id": rep_id, "modality": "camera", "evidence": evidence}


def session(count=1, assessments=None, viewpoint="side"):
    return {"repetition_count": count, "repetition_intervals": [] if count in (None, 0) else [{"rep_id": 1, "start_ms": 100, "bottom_ms": 500, "end_ms": 900}],
            "detected_viewpoint": {"value": viewpoint}, "assessments": assessments or [],
            "overall_assessment_coverage": 1 if assessments else 0, "warnings": [], "pressure_features": None}


@pytest.mark.parametrize(("state", "label"), [
    ("adequate", "No deviation detected in this check"),
    ("condition_detected", "Review suggested"),
    ("unavailable", "Not assessed"),
])
def test_supported_result_state_messages(state, label):
    assert state_label(state) == label


def test_missing_evidence_remains_controlled_and_unavailable():
    result = session(1, [assessment(result="unavailable", reason="required_landmarks_unavailable", evidence=None)])
    report = compose_feedback(result, {"answered_assessments": 0, "eligible_assessments": 1})
    assert report["primary_observation"]["criterion_id"] == "recording_quality"
    assert "full body" in report["primary_observation"]["explanation"]
    assert report["criterion_cards"][0]["measurements"] == []
    assert report["coverage"]["answered"] == 0


def test_count_can_be_available_when_all_technique_checks_are_unavailable():
    checks = [assessment(result="unavailable", reason="viewpoint_not_supported"),
              assessment("push_up_depth_proxy", "unavailable", reason="viewpoint_not_supported")]
    report = compose_feedback(session(1, checks, "front"), {"answered_assessments": 0, "eligible_assessments": 2})
    assert report["count_summary"]["count"] == 1
    assert report["primary_observation"]["criterion_id"] == "recording_quality"
    assert "fixed side view" in report["primary_observation"]["explanation"]


def test_zero_repetitions_does_not_claim_zero_errors_or_good_technique():
    report = compose_feedback(session(0), {"answered_assessments": 0, "eligible_assessments": 0})
    rendered = json.dumps(report).lower()
    assert report["count_summary"]["count"] == 0
    assert report["primary_observation"]["criterion_id"] == "recording_quality"
    assert "0 errors" not in rendered and "100% good" not in rendered


def test_flagged_depth_preserves_count_and_links_exact_repetition_interval():
    depth = assessment("push_up_depth_proxy", "condition_detected", 1, "insufficient_range_of_motion",
                       {"minimum_elbow_angle_deg": 124.0, "experimental_threshold_deg": 110.0})
    source = session(1, [depth]); before = deepcopy(source)
    report = compose_feedback(source, {"answered_assessments": 1, "eligible_assessments": 1})
    assert source == before and report["count_summary"]["count"] == 1
    assert report["primary_observation"]["interval"] == {"rep_id": 1, "start_ms": 100, "bottom_ms": 500, "end_ms": 900}
    assert "depth" in report["primary_observation"]["title"].lower()
    assert "chest-to-floor" in report["criterion_cards"][0]["limitation"]


def test_most_persistent_flag_is_selected_deterministically():
    first = assessment(evidence={"persistent_fraction": .3, "longest_persistent_duration_ms": 300})
    first["result"] = "condition_detected"; first["reason"] = "persistent_body_alignment_deviation"
    second = assessment(rep_id=2, evidence={"persistent_fraction": .6, "longest_persistent_duration_ms": 500})
    second["result"] = "condition_detected"; second["reason"] = "persistent_body_alignment_deviation"
    value = session(2, [first, second]); value["repetition_intervals"].append({"rep_id": 2, "start_ms": 1000, "bottom_ms": 1400, "end_ms": 1800})
    assert compose_feedback(value)["primary_observation"]["rep_id"] == 2


def test_missing_sensors_never_create_pressure_measurements():
    report = compose_feedback(session(1, [assessment()]))
    assert not any(card["criterion_id"].startswith("pressure") for card in report["criterion_cards"])
    pressure_scope = next(item for item in report["unsupported_criteria"] if item["criterion_id"] == "pressure_distribution")
    assert "calibrated smart-mat" in pressure_scope["reason"]


def test_policy_and_feedback_contain_no_medical_fatigue_or_prescription_claims():
    report = compose_feedback(session(1, [assessment()]))
    text = json.dumps(report).lower()
    forbidden = ["injury risk", "perfect form", "weak core", "fatigue", "next workout", "lumbar hyperextension", "spinal overload"]
    assert all(term not in text for term in forbidden)


def test_policy_matches_frozen_implementation_values():
    config = json.loads((ROOT / "configs/video_processing.json").read_text())
    assert config["camera_conditions"]["body_alignment"] == {"angle_deviation_deg": 8.0, "normalized_hip_displacement": 0.08, "minimum_persistence_fraction": 0.25, "minimum_persistence_ms": 250}
    assert config["camera_conditions"]["depth_proxy"] == {"minimum_elbow_angle_deg": 110.0, "bottom_window_ms": 250, "minimum_bottom_samples": 2}
    assert ASSESSMENT_POLICY["policy_version"] == FEEDBACK_POLICY["assessment_policy_version"]
