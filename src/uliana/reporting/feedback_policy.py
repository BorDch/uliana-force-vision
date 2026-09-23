from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "configs" / name).read_text(encoding="utf-8"))


ASSESSMENT_POLICY = _load("assessment_policy.v1.json")
FEEDBACK_POLICY = _load("feedback_policy.v1.json")
REFERENCES = {item["id"]: item for item in _load("scientific_references.v1.json")["references"]}
SUPPORTED_FEEDBACK_CRITERIA = {"body_alignment_deviation", "push_up_depth_proxy"}

QUALITY_MESSAGES = {
    "required_landmarks_unavailable": "Reposition the phone so your full body remains visible.",
    "insufficient_valid_frames": "Reposition the phone so your full body remains visible.",
    "viewpoint_not_supported": "Record a fixed side view for these alignment and depth checks.",
    "insufficient_viewpoint_evidence": "Record a fixed side view for these alignment and depth checks.",
    "pose_gap": "Keep the phone stable and avoid objects blocking your body.",
    "likely_occlusion": "Keep the phone stable and avoid objects blocking your body.",
    "low_visibility": "Reposition the phone so your full body remains visible.",
    "confirmed_incomplete_boundary_movement": "Start recording before the first repetition and stop after returning to the starting position.",
}


def state_label(result: str) -> str:
    return {"adequate": "No deviation detected in this check", "condition_detected": "Review suggested", "unavailable": "Not assessed"}[result]


def _evidence_value(assessment: dict, name: str, unit: str) -> dict | None:
    evidence = assessment.get("evidence") or {}
    value = evidence.get(name)
    return None if value is None else {"name": name, "value": value, "unit": unit}


def _criterion_card(assessment: dict, interval_by_id: dict[int, dict]) -> dict:
    criterion_id = assessment["condition"]
    policy = ASSESSMENT_POLICY["criteria"][criterion_id]
    result = assessment["result"]
    rep_id = assessment.get("rep_id")
    evidence = assessment.get("evidence") or {}
    measurements = []
    if criterion_id == "body_alignment_deviation":
        for name, unit in (("maximum_alignment_angle_deviation_deg", "degrees"), ("maximum_normalized_hip_displacement", "torso-normalized ratio"), ("persistent_fraction", "fraction"), ("longest_persistent_duration_ms", "ms")):
            item = _evidence_value(assessment, name, unit)
            if item: measurements.append(item)
    elif criterion_id == "push_up_depth_proxy":
        item = _evidence_value(assessment, "minimum_elbow_angle_deg", "degrees")
        if item: measurements.append(item)
        samples = _evidence_value(assessment, "bottom_sample_count", "samples")
        if samples: measurements.append(samples)
    elif criterion_id == "head_neck_alignment":
        for name, unit in (("maximum_normalized_deviation", "torso-lengths"), ("mean_head_deviation", "normalized units"), ("persistent_fraction", "fraction"), ("longest_persistent_duration_ms", "ms")):
            item = _evidence_value(assessment, name, unit)
            if item: measurements.append(item)
        if "head_too_high" in evidence:
            measurements.append({"name": "head_position", "value": 1, "unit": "head_too_high"})
        elif "head_too_low" in evidence:
            measurements.append({"name": "head_position", "value": -1, "unit": "head_too_low"})
    elif criterion_id == "elbow_to_torso_flare":
        item = _evidence_value(assessment, "maximum_flare_angle_deg", "degrees")
        if item: measurements.append(item)
        frac = _evidence_value(assessment, "persistent_fraction", "fraction")
        if frac: measurements.append(frac)
        dur = _evidence_value(assessment, "longest_persistent_duration_ms", "ms")
        if dur: measurements.append(dur)
    elif criterion_id == "hand_placement":
        item = _evidence_value(assessment, "mean_wrist_offset", "shoulder-widths")
        if item: measurements.append(item)
        max_offset = _evidence_value(assessment, "maximum_wrist_offset", "shoulder-widths")
        if max_offset: measurements.append(max_offset)
        frac = _evidence_value(assessment, "persistent_fraction", "fraction")
        if frac: measurements.append(frac)
    return {
        "criterion_id": criterion_id,
        "criterion_name": policy["plain_name"],
        "rep_id": rep_id,
        "result": result,
        "status_label": state_label(result),
        "reason": assessment.get("reason"),
        "interval": interval_by_id.get(rep_id),
        "measurements": measurements,
        "threshold": evidence.get("experimental_thresholds") or evidence.get("experimental_threshold_deg") or evidence.get("experimental_threshold"),
        "measurement_definition": policy["measurement_definition"],
        "limitation": policy.get("limitation"),
        "reference_ids": policy.get("evidence_references", []),
        "validation_status": policy["validation_status"],
    }


def compose_feedback(result: dict, metrics: dict | None = None, research_preview: dict | None = None) -> dict:
    metrics = metrics or {}
    research_preview = research_preview or {}
    intervals = result.get("repetition_intervals") or []
    interval_by_id = {item["rep_id"]: item for item in intervals}
    card_inputs = [*result.get("assessments", []), *research_preview.get("assessments", [])]
    cards = [_criterion_card(item, interval_by_id) for item in card_inputs if item.get("condition") in ASSESSMENT_POLICY["criteria"]]
    supported = [item for item in result.get("assessments", []) if item.get("condition") in SUPPORTED_FEEDBACK_CRITERIA]
    flagged = [item for item in supported if item.get("result") == "condition_detected"]
    unavailable = [item for item in supported if item.get("result") == "unavailable"]
    quality_reasons = list(dict.fromkeys([*(result.get("warnings") or []), *(item.get("reason") for item in unavailable if item.get("reason"))]))
    guidance = list(dict.fromkeys(QUALITY_MESSAGES[reason] for reason in quality_reasons if reason in QUALITY_MESSAGES))
    reliable = result.get("repetition_count") is not None and any(item.get("result") != "unavailable" for item in supported)
    criterion_order = {item: index for index, item in enumerate(FEEDBACK_POLICY["priority"])}
    flagged.sort(key=lambda item: (
        -(item.get("evidence") or {}).get("persistent_fraction", 0),
        -(item.get("evidence") or {}).get("longest_persistent_duration_ms", 0),
        item.get("rep_id") or 10**9,
        criterion_order.get(item.get("condition"), 10**9),
    ))
    if not reliable:
        primary = {"criterion_id": "recording_quality", "title": "Recording guidance", "explanation": guidance[0] if guidance else "The available camera evidence was insufficient for a movement assessment.", "action": guidance[0] if guidance else "Record a fixed side view with your full body visible.", "rep_id": None, "interval": None}
    elif flagged:
        selected = flagged[0]; policy = ASSESSMENT_POLICY["criteria"][selected["condition"]]; rep_id = selected.get("rep_id")
        primary = {"criterion_id": selected["condition"], "title": policy["flagged_title"].format(rep_id=rep_id), "explanation": policy["flagged_explanation"], "action": policy["action"], "rep_id": rep_id, "interval": interval_by_id.get(rep_id)}
    else:
        primary = {"criterion_id": "available_checks", "title": "No deviation detected in the checks available for this recording.", "explanation": "Available results apply only to the listed camera checks.", "action": "Repeat the same camera setup next session for a descriptive comparison.", "rep_id": None, "interval": None}
    count = result.get("repetition_count")
    supporting = []
    if count is not None: supporting.append(f"{count} complete repetitions detected. A completed movement cycle is not a certification of technique.")
    if unavailable: supporting.append(f"{len(unavailable)} per-repetition checks were not assessed; missing assessments were not converted to passes.")
    next_steps = [primary["action"], *guidance]
    next_steps = list(dict.fromkeys(next_steps))[:FEEDBACK_POLICY["maximum_next_steps"]]
    reference_ids = sorted({ref for card in cards for ref in card["reference_ids"]})
    return {
        "schema_version": "1.0",
        "feedback_policy_version": FEEDBACK_POLICY["policy_version"],
        "assessment_policy_version": ASSESSMENT_POLICY["policy_version"],
        "count_summary": {"count": count, "available": count is not None, "message": ASSESSMENT_POLICY["criteria"]["completed_movement_cycles"]["display"]["available"].format(count=count) if count is not None else ASSESSMENT_POLICY["criteria"]["completed_movement_cycles"]["display"]["unavailable"], "limitation": ASSESSMENT_POLICY["criteria"]["completed_movement_cycles"]["limitation"]},
        "coverage": {"answered": metrics.get("answered_assessments"), "eligible": metrics.get("eligible_assessments"), "fraction": result.get("overall_assessment_coverage"), "definition": ASSESSMENT_POLICY["coverage_definition"]},
        "primary_observation": primary,
        "supporting_observations": supporting[:FEEDBACK_POLICY["maximum_supporting_observations"]],
        "next_steps": next_steps,
        "criterion_cards": cards,
        "unsupported_criteria": ASSESSMENT_POLICY["unsupported_criteria"],
        "references": [REFERENCES[item] for item in reference_ids],
        "limitations": ["Only body alignment and range of motion can drive primary feedback.", "Head position, elbow flare and camera-only hand placement are research previews pending trainer validation.", "Camera proxies are not direct force measurements or validated 3D joint measurements."],
    }
