"""Validated language-only summaries for deterministic ULIANA results."""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from jsonschema import Draft202012Validator

POLICY_VERSION = "coach-summary.v1"
SYSTEM_PROMPT = """You are ULIANA’s exercise-session explainer. Convert structured camera-analysis facts into concise, supportive user feedback. Use only the supplied facts. Do not infer additional movement problems, medical risks, fatigue, pain, injury probability or workout prescriptions. Do not turn unavailable assessments into positive results. Preserve all counts and assessment states exactly. Recommend reviewing specific repetitions and repeating the same camera setup when supported. Return only the required JSON object."""
SUPPORTED_CRITERIA = {"body_alignment", "range_of_motion"}
FORBIDDEN = re.compile(r"\b(injur(?:y|ies|ed)|fatigue|pain|diagnos(?:e|is|tic)|medical|disease|risk|safe technique|perfect technique|biomechanical diagnosis|weak core|prescri(?:be|ption))\b", re.I)
UNSUPPORTED = re.compile(r"\b(head position|neck alignment|elbow flare|hand placement|pressure balance|load balance|contact position|knee alignment|back position|wrist alignment|shoulder stability)\b", re.I)

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["headline", "summary", "what_went_well", "main_focus", "next_session_plan", "comparison_summary"],
    "properties": {
        "headline": {"type": "string", "minLength": 1},
        "summary": {"type": "string", "minLength": 1},
        "what_went_well": {"type": "string", "minLength": 1},
        "main_focus": {"type": "string", "minLength": 1},
        "next_session_plan": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "string", "minLength": 1}},
        "comparison_summary": {"type": "string", "minLength": 1}
    }
}


class CoachSummaryProvider(Protocol):
    def generate(self, system_prompt: str, facts: dict, timeout_seconds: float) -> str: ...


class OllamaProvider:
    """Local Ollama JSON provider; receives facts only, never video or landmarks."""
    def __init__(self, model: str, endpoint: str = "http://127.0.0.1:11434/api/chat"):
        if not model:
            raise ValueError("ULIANA_LLM_MODEL is required for the local provider")
        self.model, self.endpoint = model, endpoint

    def generate(self, system_prompt: str, facts: dict, timeout_seconds: float) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "format": OUTPUT_SCHEMA,
            "options": {"temperature": 0.1},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(facts, separators=(",", ":"), sort_keys=True)},
            ],
        }
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            value = json.loads(response.read())
        return value["message"]["content"]


def representative(assessments: list[dict], criterion: str) -> int | None:
    flagged = [item for item in assessments if item.get("condition") == criterion and item.get("result") == "condition_detected" and item.get("rep_id") is not None]
    flagged.sort(key=lambda item: (-float((item.get("evidence") or {}).get("persistent_fraction", 0)), -float((item.get("evidence") or {}).get("longest_persistent_duration_ms", 0)), item["rep_id"]))
    return flagged[0]["rep_id"] if flagged else None


def build_coach_facts(result: dict, comparison: dict | None = None, smart_mat_connected: bool = False) -> dict:
    assessments = result.get("assessments", [])
    intervals = {item.get("rep_id"): item for item in result.get("repetition_intervals", [])}
    criteria = {}
    for source, name in (("body_alignment_deviation", "body_alignment"), ("push_up_depth_proxy", "range_of_motion")):
        rows = [item for item in assessments if item.get("condition") == source]
        representative_rep = representative(rows, source)
        interval = intervals.get(representative_rep, {})
        timestamp_ms = interval.get("bottom_ms", interval.get("start_ms"))
        criteria[name] = {
            "assessed_repetitions": sum(item.get("result") != "unavailable" for item in rows),
            "flagged_repetitions": sum(item.get("result") == "condition_detected" for item in rows),
            "representative_repetition": representative_rep,
            "representative_timestamp_seconds": round(timestamp_ms / 1000, 3) if timestamp_ms is not None else None,
        }
    return {
        "exercise": (result.get("exercise") or "push-up").replace("-", "_"),
        "completed_repetitions": result.get("repetition_count"),
        "viewpoint": (result.get("detected_viewpoint") or {}).get("value", "unknown"),
        "duration_seconds": result.get("duration_seconds"),
        "criteria": criteria,
        "comparison": comparison or {"available": False, "reason": "no_previous_compatible_session"},
        "smart_mat_connected": bool(smart_mat_connected),
        "limitations": [
            "camera measurements are view-dependent",
            "range of motion is estimated from elbow angle",
            "pressure distribution is unavailable" if not smart_mat_connected else "pressure measurements depend on calibrated sensor data",
        ],
    }


class DeterministicCoachSummaryFormatter:
    def format(self, facts: dict) -> dict:
        count = facts["completed_repetitions"]
        alignment = facts["criteria"]["body_alignment"]
        motion = facts["criteria"]["range_of_motion"]
        flagged = alignment["flagged_repetitions"] + motion["flagged_repetitions"]
        representative_rep = alignment["representative_repetition"] or motion["representative_repetition"]
        if count is None:
            headline = "Session summary unavailable"
            summary = "The camera did not provide a reliable repetition count. Record again with your full body visible."
        elif flagged:
            headline = "One clear focus for your next session"
            summary = f"You completed {count} repetitions. Review repetition {representative_rep} for the clearest supported camera observation."
        else:
            headline = "No issue detected in the available checks"
            summary = f"You completed {count} repetitions. No issue was detected in the supported checks that were available."
        if motion["assessed_repetitions"] and not motion["flagged_repetitions"]:
            positive = "No issue was detected in the available range-of-motion check."
        elif alignment["assessed_repetitions"] and not alignment["flagged_repetitions"]:
            positive = "No issue was detected in the available body-alignment check."
        else:
            positive = "Your complete repetitions were counted from the recorded movement."
        if alignment["flagged_repetitions"]:
            focus = f"Review repetition {alignment['representative_repetition']} and focus on keeping shoulders, hips and ankles aligned."
            action = "Keep shoulders, hips and ankles aligned through the movement."
        elif motion["flagged_repetitions"]:
            focus = f"Review repetition {motion['representative_repetition']} and check your lowering range."
            action = "Review the bottom position using the camera-based elbow-angle estimate."
        elif not motion["assessed_repetitions"]:
            focus = "Range of motion was unavailable; do not treat it as a positive result."
            action = "Keep the elbow visible near the bottom position."
        else:
            focus = "Repeat the same setup to build a comparable history."
            action = "Use the same movement and camera setup next time."
        comparison = facts["comparison"]
        if comparison.get("available"):
            comparison_text = comparison.get("summary") or "This session was compared with the previous compatible session."
        elif comparison.get("reason") == "camera_setup_changed":
            comparison_text = "The camera setup changed, so this session was not compared with the previous one."
        else:
            comparison_text = "Complete another session with the same camera setup to start a comparison."
        return {"headline": headline, "summary": summary, "what_went_well": positive, "main_focus": focus, "next_session_plan": [action, "Use the same side camera angle with your full body visible."], "comparison_summary": comparison_text}


class CoachSummaryValidator:
    def validate(self, value: dict, facts: dict) -> dict:
        errors = list(Draft202012Validator(OUTPUT_SCHEMA).iter_errors(value))
        if errors:
            raise ValueError("invalid coach summary schema")
        text = " ".join([value["headline"], value["summary"], value["what_went_well"], value["main_focus"], *value["next_session_plan"], value["comparison_summary"]])
        if len(text.split()) > 80:
            raise ValueError("coach summary exceeds 80 words")
        if FORBIDDEN.search(text):
            raise ValueError("coach summary contains forbidden medical or diagnostic language")
        if UNSUPPORTED.search(text):
            raise ValueError("coach summary introduces an unsupported criterion")
        allowed_numbers = {str(value) for value in _numbers(facts)}
        for number in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", text):
            if number not in allowed_numbers:
                raise ValueError("coach summary contains an invented number")
        return value


def _numbers(value):
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, dict):
        return [number for item in value.values() for number in _numbers(item)]
    if isinstance(value, list):
        return [number for item in value for number in _numbers(item)]
    return []


@dataclass
class LLMCoachSummaryFormatter:
    provider: CoachSummaryProvider
    timeout_seconds: float = 8
    validator: CoachSummaryValidator = CoachSummaryValidator()

    def format(self, facts: dict) -> dict:
        raw = self.provider.generate(SYSTEM_PROMPT, facts, self.timeout_seconds)
        return self.validator.validate(json.loads(raw), facts)


def facts_hash(facts: dict) -> str:
    return hashlib.sha256(json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def coach_summary(facts: dict, session_id: str, cache_file: Path, provider: CoachSummaryProvider | None = None) -> dict:
    key = hashlib.sha256(f"{session_id}:{POLICY_VERSION}:{facts_hash(facts)}".encode()).hexdigest()
    if cache_file.is_file():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if cached.get("cache_key") == key:
            return cached["summary"]
    fallback = DeterministicCoachSummaryFormatter().format(facts)
    summary = fallback
    source = "deterministic"
    enabled = os.getenv("ULIANA_LLM_ENABLED", "0") == "1"
    if enabled and provider is not None:
        try:
            summary = LLMCoachSummaryFormatter(provider, float(os.getenv("ULIANA_LLM_TIMEOUT_SECONDS", "8"))).format(facts)
            source = "llm"
        except Exception:
            summary, source = fallback, "deterministic_fallback"
    CoachSummaryValidator().validate(summary, facts)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_file.with_suffix(cache_file.suffix + ".tmp")
    temporary.write_text(json.dumps({"cache_key": key, "policy_version": POLICY_VERSION, "facts_hash": facts_hash(facts), "source": source, "summary": summary}, indent=2)+"\n", encoding="utf-8")
    temporary.replace(cache_file)
    return summary


def configured_provider() -> CoachSummaryProvider | None:
    if os.getenv("ULIANA_LLM_ENABLED", "0") != "1":
        return None
    if os.getenv("ULIANA_LLM_PROVIDER", "local") == "local":
        return OllamaProvider(os.getenv("ULIANA_LLM_MODEL", ""))
    raise ValueError("unsupported ULIANA_LLM_PROVIDER")
