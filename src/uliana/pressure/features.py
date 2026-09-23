from __future__ import annotations

from collections import defaultdict

from uliana.contracts.models import PressureObservation


def _impulse(items: list[PressureObservation]) -> float | None:
    ordered = sorted((item.timestamp_ms, item.calibrated_force_n) for item in items if item.calibrated_force_n is not None)
    if len(ordered) < 2: return None
    return sum((b_t - a_t) / 1000 * (a_v + b_v) / 2 for (a_t, a_v), (b_t, b_v) in zip(ordered, ordered[1:]))


def compute_pressure_features(observations: list[PressureObservation], config: dict,
                              raw_weighted_centre: bool = False) -> dict:
    grouped: dict[str, list[PressureObservation]] = defaultdict(list)
    by_time: dict[int, list[PressureObservation]] = defaultdict(list)
    for item in observations:
        grouped[item.channel_id].append(item); by_time[item.timestamp_ms].append(item)
    per_channel = {}
    expected_rate = config.get("nominal_sampling_rate_hz")
    starts = [item.timestamp_ms for item in observations]; duration = max(starts) - min(starts) if starts else 0
    expected_samples = duration / 1000 * expected_rate + 1 if expected_rate and observations else None
    for channel, items in sorted(grouped.items()):
        calibrated = [item.calibrated_force_n for item in items if item.calibrated_force_n is not None]
        coverage = min(1.0, len(items) / expected_samples) if expected_samples else None
        per_channel[channel] = {
            "sample_count": len(items), "mean_raw": sum(x.raw_value for x in items) / len(items),
            "maximum_raw": max(x.raw_value for x in items),
            "mean_force_n": sum(calibrated) / len(calibrated) if len(calibrated) == len(items) else None,
            "maximum_force_n": max(calibrated) if len(calibrated) == len(items) else None,
            "impulse_ns": _impulse(items) if len(calibrated) == len(items) else None,
            "sampling_coverage": coverage, "missing_data_fraction": 1 - coverage if coverage is not None else None,
        }
    aggregates = []
    for timestamp, items in sorted(by_time.items()):
        all_calibrated = bool(items) and all(item.calibrated_force_n is not None for item in items)
        calibrated_total = sum(item.calibrated_force_n for item in items) if all_calibrated else None
        raw_total = sum(item.raw_value for item in items)
        active = sum((item.calibrated_force_n or 0) > 0 if all_calibrated else item.raw_value != 0 for item in items)
        centre = None; centre_kind = None
        positioned = all(item.grid_position is not None for item in items)
        if positioned and all_calibrated and calibrated_total and calibrated_total > 0:
            centre = {"row": sum(item.grid_position.row * item.calibrated_force_n for item in items) / calibrated_total,
                      "column": sum(item.grid_position.column * item.calibrated_force_n for item in items) / calibrated_total}
            centre_kind = "force_weighted_physical"
        elif positioned and raw_weighted_centre and raw_total != 0:
            centre = {"row": sum(item.grid_position.row * item.raw_value for item in items) / raw_total,
                      "column": sum(item.grid_position.column * item.raw_value for item in items) / raw_total}
            centre_kind = "raw_signal_weighted_non_physical"
        aggregates.append({"timestamp_ms": timestamp, "total_calibrated_force_n": calibrated_total,
                           "total_raw_signal": raw_total, "active_cell_count": active,
                           "centre_of_pressure": centre, "centre_kind": centre_kind})
    region_result = {"result": "unavailable", "reason": "regions_not_configured"}
    regions = config.get("regions") or {}
    if "left_palm" in regions and "right_palm" in regions:
        required = set(regions["left_palm"] + regions["right_palm"])
        if not required <= set(grouped): region_result = {"result": "unavailable", "reason": "required_region_channels_missing"}
        elif any(any(item.calibrated_force_n is None for item in grouped[channel]) for channel in required):
            region_result = {"result": "unavailable", "reason": "required_region_channels_uncalibrated"}
        elif any((per_channel[channel]["sampling_coverage"] or 0) < config.get("minimum_region_coverage", .7) for channel in required):
            region_result = {"result": "unavailable", "reason": "insufficient_region_coverage"}
        else:
            means = {name: sum(per_channel[channel]["mean_force_n"] for channel in channels)
                     for name, channels in (("left_palm", regions["left_palm"]), ("right_palm", regions["right_palm"]))}
            total = means["left_palm"] + means["right_palm"]
            if total <= 0: region_result = {"result": "unavailable", "reason": "near_zero_region_force"}
            else:
                imbalance = abs(means["left_palm"] - means["right_palm"]) / total * 100
                region_result = {"result": "available", "definition": "abs(left-right)/(left+right)*100",
                    "left_mean_force_n": means["left_palm"], "right_mean_force_n": means["right_palm"],
                    "imbalance_percent": imbalance, "above_configured_alert_threshold": imbalance > config.get("imbalance_alert_percent", 10)}
    return {"per_channel": per_channel, "time_series": aggregates, "region_balance": region_result,
            "limitations": ["Pressure asymmetry is descriptive and is not by itself a technique classification."]}
