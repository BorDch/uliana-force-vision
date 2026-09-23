import json
import random
from dataclasses import asdict
from pathlib import Path

from jsonschema import validate

from uliana.reliability import assess
from uliana.scoring import component_scores, decide
from uliana.session import summarize
from uliana.simulator import generate_experiment, generate_repetition
from uliana.synchronization import synchronize
from uliana.types import AnalysisResult


def test_schema_compatible_packet(config):
    rep = generate_repetition(1, 1, "balanced", config, random.Random(42))
    synced, _ = synchronize(rep.pose_samples, rep.force_samples, 50)
    summary = summarize(1, synced)
    packet = AnalysisResult("1.0", "toy_simulator", "test", 1000, 1, "up",
        {"left_force_n": 200, "right_force_n": 200, "asymmetry_percent": 0, "elbow_angle_deg": 160, "body_line_error_deg": 2},
        component_scores(summary, config), asdict(decide(summary, assess(synced, config), config)))
    schema = json.loads((Path(__file__).parents[1] / "schemas" / "analysis-result.schema.json").read_text())
    validate(packet.to_dict(), schema)


def test_reproducible_with_same_seed(config):
    first = generate_experiment(config)[:2]
    second = generate_experiment(config)[:2]
    assert first == second

