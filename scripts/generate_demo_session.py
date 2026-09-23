#!/usr/bin/env python3
"""Generate dashboard-replayable JSONL (one schema-compatible packet per line)."""
from run_toy_experiments import ROOT, evaluate
from uliana.config import load_config
from uliana.session import write_jsonl

config = load_config(ROOT / "configs" / "toy_experiment.json")
_, _, packets, _ = evaluate(config, evaluation_participants={10})
destination = ROOT / "artifacts" / "toy_experiments" / "sample_session.jsonl"
destination.parent.mkdir(parents=True, exist_ok=True)
write_jsonl(destination, packets)
print(destination)

