from __future__ import annotations

from .metrics import clamp
from .types import FeedbackDecision, ReliabilityState, RepetitionSummary


def component_scores(summary: RepetitionSummary, config: dict) -> dict[str, float]:
    limits = config["thresholds"]
    asymmetry = summary.mean_asymmetry_percent if summary.mean_asymmetry_percent is not None else 100
    balance = clamp(100 - asymmetry * 3.2)
    depth = clamp(100 - max(0, summary.minimum_elbow_angle_deg - 92) * 3.0)
    alignment = clamp(100 - summary.maximum_body_line_error_deg * 5.2)
    weights = config["scoring"]
    overall = clamp(weights["balance_weight"] * balance + weights["depth_weight"] * depth + weights["alignment_weight"] * alignment)
    return {"overall": round(overall), "balance": round(balance), "depth": round(depth), "alignment": round(alignment)}


def decide(summary: RepetitionSummary, reliability: ReliabilityState, config: dict, mode: str = "fused") -> FeedbackDecision:
    limits = config["thresholds"]
    if mode in ("fused", "force") and not reliability.force_reliable:
        return FeedbackDecision("Check/calibrate force sensors", 0.0, True, reliability.reason or "force_unreliable")
    if mode in ("fused", "camera") and not reliability.pose_reliable:
        return FeedbackDecision("Reposition the camera", 0.0, True, reliability.reason or "pose_confidence_below_limit")
    if (mode in ("fused", "force") and summary.mean_asymmetry_percent is not None
            and summary.mean_asymmetry_percent > limits["asymmetry_percent"]
            and summary.asymmetry_persistent_ms >= limits["persistence_ms"]):
        cue = "Shift weight right." if (summary.mean_left_force_n or 0) > (summary.mean_right_force_n or 0) else "Shift weight left."
        return FeedbackDecision(cue, 0.9, False, "persistent_force_asymmetry")
    if mode in ("fused", "camera") and summary.minimum_elbow_angle_deg > limits["insufficient_depth_angle_deg"]:
        return FeedbackDecision("Increase movement depth.", 0.85, False, "insufficient_depth")
    if (mode in ("fused", "camera") and summary.maximum_body_line_error_deg > limits["body_line_error_deg"]
            and summary.body_line_error_persistent_ms >= limits["persistence_ms"]):
        return FeedbackDecision("Keep your body straight.", 0.85, False, "body_line_error")
    return FeedbackDecision("Good repetition.", 0.9, False, None)
