from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(path: str | Path = "configs/toy_experiment.json") -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        config = json.load(handle)
    if "participants" in config and (config["participants"] < 1 or config["repetitions_per_participant"] < 1):
        raise ValueError("participants and repetitions_per_participant must be positive")
    weights = config.get("scoring")
    if weights is not None and abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("scoring weights must sum to 1")
    return config
