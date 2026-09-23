from __future__ import annotations

import statistics

from uliana.contracts.models import SynchronizationReport
from .alignment import Alignment


def synchronization_report(alignment: Alignment, matching: dict | None = None,
                           minimum_matched_fraction: float = .7) -> SynchronizationReport:
    matching = matching or {}
    residuals = sorted(alignment.anchor_residuals_ms + list(matching.get("errors_ms", [])))
    median = statistics.median(residuals) if residuals else None
    p95 = residuals[min(len(residuals)-1, int(.95*len(residuals)))] if residuals else None
    matched = matching.get("matched_fraction")
    if not alignment.available: status = "unavailable"
    elif matched is None: status = "acceptable"
    else: status = "acceptable" if matched >= minimum_matched_fraction else "poor"
    warnings = list(alignment.warnings)
    if status == "poor": warnings.append("low_matched_fraction")
    return SynchronizationReport(status, alignment.method, alignment.offset_ms, alignment.drift_ppm,
        matched, median, p95, alignment.reason, matching.get("maximum_gap_ms"), warnings)
