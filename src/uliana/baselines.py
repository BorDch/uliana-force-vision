from __future__ import annotations

from .scoring import decide
from .types import FeedbackDecision, ReliabilityState, RepetitionSummary


def camera_only(summary: RepetitionSummary, reliability: ReliabilityState, config: dict) -> FeedbackDecision:
    return decide(summary, reliability, config, "camera")


def force_only(summary: RepetitionSummary, reliability: ReliabilityState, config: dict) -> FeedbackDecision:
    return decide(summary, reliability, config, "force")


def fused(summary: RepetitionSummary, reliability: ReliabilityState, config: dict) -> FeedbackDecision:
    return decide(summary, reliability, config, "fused")

