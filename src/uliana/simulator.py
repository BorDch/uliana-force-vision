from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .types import ForceSample, PoseSample


@dataclass(frozen=True)
class SyntheticRepetition:
    participant_id: int
    scenario: str
    force_samples: list[ForceSample]
    pose_samples: list[PoseSample]
    ground_truth: str


def generate_repetition(participant_id: int, rep_index: int, scenario: str, config: dict, rng: random.Random,
                        severity: float = 1.0) -> SyntheticRepetition:
    duration = rng.uniform(*config["duration_seconds"])
    start = (participant_id * config["repetitions_per_participant"] + rep_index) * 5000
    body_weight = rng.uniform(550, 900)
    base_total = body_weight * rng.uniform(.43, .58)
    participant_bias = rng.gauss(0, .018)
    force_noise = config["noise"]["force_std_n"] * severity
    pose_noise = config["noise"]["pose_angle_std_deg"] * severity
    jitter = config["noise"]["timestamp_jitter_ms"] * severity
    missing = min(.45, config["noise"]["missing_probability"] * severity)
    force_samples: list[ForceSample] = []
    force_count = int(duration * config["force_hz"]) + 1
    for i in range(force_count):
        progress = i / max(1, force_count - 1)
        timestamp = start + round(i * 1000 / config["force_hz"] + rng.gauss(0, jitter))
        if scenario == "delayed_force_samples": timestamp += round(duration * 1000 + 100)
        if (scenario == "missing_force_samples" and rng.random() < .90) or rng.random() < missing:
            continue
        total = base_total + 18 * math.sin(progress * 2 * math.pi) + rng.gauss(0, force_noise)
        bias = participant_bias
        if scenario in ("left_overload", "left_overload_and_body_line_error"):
            bias += .11
        if scenario in ("right_overload", "right_overload_and_insufficient_depth"):
            bias -= .11
        left = total * (.5 + bias) + rng.gauss(0, force_noise / 2)
        right = total - left + rng.gauss(0, force_noise / 2)
        valid, error = True, None
        if scenario == "sensor_saturation": left, valid, error = config["reliability"]["max_force_n"] + 40, False, "sensor_saturation"
        if scenario == "near_zero_total_force": left, right, valid, error = 2.0, 2.5, False, "near_zero_total_force"
        force_samples.append(ForceSample(timestamp, max(0, left), max(0, right), valid, error))
    pose_samples: list[PoseSample] = []
    pose_count = int(duration * config["pose_hz"]) + 1
    for i in range(pose_count):
        progress = i / max(1, pose_count - 1)
        # Smooth UP -> DOWN -> UP trajectory with endpoints 165 degrees.
        min_angle = 122 if scenario in ("insufficient_depth", "right_overload_and_insufficient_depth") else 92
        angle = min_angle + (165 - min_angle) * (1 + math.cos(progress * 2 * math.pi)) / 2 + rng.gauss(0, pose_noise)
        body_error = 12 if scenario in ("body_line_error", "left_overload_and_body_line_error") else rng.uniform(2, 5)
        confidence = rng.uniform(.86, .98)
        if scenario == "low_pose_confidence": confidence = rng.uniform(.35, .58)
        timestamp = start + round(i * 1000 / config["pose_hz"] + rng.gauss(0, jitter))
        pose_samples.append(PoseSample(timestamp, angle, max(0, body_error + rng.gauss(0, pose_noise / 3)), confidence))
    return SyntheticRepetition(participant_id, scenario, force_samples, pose_samples, scenario)


def generate_experiment(config: dict, severity: float = 1.0) -> list[SyntheticRepetition]:
    rng = random.Random(config["seed"] + round(severity * 1000))
    scenarios = config["scenarios"]
    return [generate_repetition(p, r, scenarios[(p * config["repetitions_per_participant"] + r) % len(scenarios)], config, rng, severity)
            for p in range(config["participants"]) for r in range(config["repetitions_per_participant"])]
