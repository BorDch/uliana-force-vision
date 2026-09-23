import json
import pytest

from uliana.reporting.coach_summary import (
    CoachSummaryValidator,
    DeterministicCoachSummaryFormatter,
    LLMCoachSummaryFormatter,
    build_coach_facts,
    coach_summary,
)


def assessment(condition, result, rep, persistent=0):
    return {"condition": condition, "result": result, "rep_id": rep, "confidence": .9, "evidence": {"persistent_fraction": persistent}}


def session(alignment="adequate", motion="adequate", viewpoint="side"):
    return {"exercise": "push-up", "repetition_count": 2, "duration_seconds": 3.2, "detected_viewpoint": {"value": viewpoint}, "assessments": [assessment("body_alignment_deviation", alignment, 1, .7), assessment("push_up_depth_proxy", motion, 1), assessment("body_alignment_deviation", "adequate", 2), assessment("push_up_depth_proxy", "adequate", 2)]}


class Provider:
    def __init__(self, value=None, error=None): self.value, self.error, self.calls = value, error, 0
    def generate(self, system_prompt, facts, timeout_seconds):
        self.calls += 1
        if self.error: raise self.error
        return self.value


def valid_output():
    return {"headline": "Review one repetition", "summary": "You completed 2 repetitions. Review repetition 1.", "what_went_well": "No issue was detected in the range-of-motion check.", "main_focus": "Keep shoulders, hips and ankles aligned.", "next_session_plan": ["Review repetition 1.", "Use the same side camera angle."], "comparison_summary": "Complete another comparable session."}


def test_alignment_flag_uses_representative_repetition():
    value = session("condition_detected")
    value["repetition_intervals"] = [{"rep_id": 1, "start_ms": 500, "bottom_ms": 1250, "end_ms": 1900}]
    facts = build_coach_facts(value)
    output = DeterministicCoachSummaryFormatter().format(facts)
    assert facts["criteria"]["body_alignment"]["representative_repetition"] == 1
    assert facts["criteria"]["body_alignment"]["representative_timestamp_seconds"] == 1.25
    assert "repetition 1" in output["summary"].lower()


def test_no_supported_flags_avoids_perfect_claim():
    output = DeterministicCoachSummaryFormatter().format(build_coach_facts(session()))
    assert "no issue was detected" in output["summary"].lower()
    assert "perfect" not in json.dumps(output).lower()


def test_unavailable_range_is_not_converted_to_positive():
    value = session()
    value["assessments"] = [item for item in value["assessments"] if item["condition"] != "push_up_depth_proxy"] + [assessment("push_up_depth_proxy", "unavailable", 1), assessment("push_up_depth_proxy", "unavailable", 2)]
    output = DeterministicCoachSummaryFormatter().format(build_coach_facts(value))
    assert "unavailable" in output["main_focus"].lower()


def test_changed_camera_angle_and_compatible_comparison_copy():
    changed = build_coach_facts(session(), {"available": False, "reason": "camera_setup_changed"})
    assert "camera setup changed" in DeterministicCoachSummaryFormatter().format(changed)["comparison_summary"].lower()
    compatible = build_coach_facts(session(), {"available": True, "summary": "Previous comparable session: 2 repetitions; this session: 2."})
    assert DeterministicCoachSummaryFormatter().format(compatible)["comparison_summary"].startswith("Previous")


def test_disconnected_smart_mat_is_explicit():
    facts = build_coach_facts(session(), smart_mat_connected=False)
    assert facts["smart_mat_connected"] is False
    assert "pressure distribution is unavailable" in facts["limitations"]


@pytest.mark.parametrize("raw", ["not json", json.dumps({"headline": "missing fields"})])
def test_malformed_llm_response_rejected(raw):
    with pytest.raises((ValueError, json.JSONDecodeError)):
        LLMCoachSummaryFormatter(Provider(raw)).format(build_coach_facts(session("condition_detected")))


def test_invented_values_and_forbidden_language_rejected():
    facts = build_coach_facts(session("condition_detected"))
    invented = valid_output(); invented["summary"] = "You completed 99 repetitions."
    with pytest.raises(ValueError): CoachSummaryValidator().validate(invented, facts)
    medical = valid_output(); medical["main_focus"] = "This prevents injury risk."
    with pytest.raises(ValueError): CoachSummaryValidator().validate(medical, facts)


@pytest.mark.parametrize("error", [TimeoutError(), RuntimeError("provider failed")])
def test_timeout_and_provider_failure_fall_back(monkeypatch, tmp_path, error):
    monkeypatch.setenv("ULIANA_LLM_ENABLED", "1")
    facts = build_coach_facts(session("condition_detected"))
    output = coach_summary(facts, "session-1", tmp_path / "summary.json", Provider(error=error))
    assert output == DeterministicCoachSummaryFormatter().format(facts)


def test_disabled_is_deterministic_and_does_not_call_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("ULIANA_LLM_ENABLED", "0")
    provider = Provider(json.dumps(valid_output()))
    facts = build_coach_facts(session("condition_detected"))
    assert coach_summary(facts, "session-1", tmp_path / "summary.json", provider) == DeterministicCoachSummaryFormatter().format(facts)
    assert provider.calls == 0


def test_valid_llm_result_is_cached_stably(monkeypatch, tmp_path):
    monkeypatch.setenv("ULIANA_LLM_ENABLED", "1")
    provider = Provider(json.dumps(valid_output()))
    facts = build_coach_facts(session("condition_detected"))
    cache = tmp_path / "summary.json"
    first = coach_summary(facts, "session-1", cache, provider)
    provider.value = "not json"
    second = coach_summary(facts, "session-1", cache, provider)
    assert first == second
    assert provider.calls == 1
