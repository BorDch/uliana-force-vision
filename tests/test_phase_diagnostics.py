from copy import deepcopy
from pathlib import Path

import pytest

from uliana.config import load_config
from uliana.video.phases import SelectedSignal, phase_thresholds


CONFIG = load_config(Path(__file__).parents[1] / "artifacts/real_recordings/development_baseline/config_snapshot.json")


def test_baseline_thresholds_remain_min_max_based():
    selected = SelectedSignal("bilateral_elbow_angle", [(0, 0.0), (1, 1.0), (2, 2.0), (3, 100.0)], 1, 100, 0, 1)
    thresholds = phase_thresholds(selected, CONFIG)
    assert thresholds["range_low"] == 0
    assert thresholds["range_high"] == 100
    assert thresholds["top"] == pytest.approx(78)
    assert thresholds["bottom"] == pytest.approx(30)


def test_optional_robust_quantiles_do_not_mutate_baseline_config():
    selected = SelectedSignal("bilateral_elbow_angle", [(0, 0.0), (1, 1.0), (2, 2.0), (3, 100.0)], 1, 100, 0, 1)
    candidate = deepcopy(CONFIG)
    candidate["phase_segmentation"]["threshold_quantiles"] = {"lower": .2, "upper": .8}
    thresholds = phase_thresholds(selected, candidate)
    assert thresholds["range_low"] == pytest.approx(.6)
    assert thresholds["range_high"] == pytest.approx(41.2)
    assert "threshold_quantiles" not in CONFIG["phase_segmentation"]


def test_quantile_thresholds_resist_extreme_terminal_extension():
    selected = SelectedSignal("x", list(enumerate([0, 0, 10, 20, 30, 40, 50, 60, 70, 1000])), 1, 1000, 0, 1)
    candidate = deepcopy(CONFIG)
    candidate["phase_segmentation"].update({"top_fraction": .65, "threshold_quantiles": {"lower": .2, "upper": .8}})
    robust = phase_thresholds(selected, candidate)
    extrema = phase_thresholds(selected, CONFIG)
    assert robust["range_high"] < 100
    assert robust["top"] < extrema["top"] / 5
