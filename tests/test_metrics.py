import pytest

from uliana.metrics import asymmetry_percent
from uliana.scoring import component_scores
from uliana.types import RepetitionSummary


def summary(**changes):
    values = dict(rep_id=1, mean_left_force_n=220, mean_right_force_n=180, mean_asymmetry_percent=10,
                  max_asymmetry_percent=10, left_impulse_ns=200, right_impulse_ns=180,
                  minimum_elbow_angle_deg=92, maximum_body_line_error_deg=3, mean_pose_confidence=.9)
    values.update(changes)
    return RepetitionSummary(**values)


def test_force_asymmetry_and_near_zero():
    assert asymmetry_percent(60, 40) == pytest.approx(20)
    assert asymmetry_percent(2, 3) is None
    with pytest.raises(ValueError): asymmetry_percent(-1, 20)


def test_score_bounds(config):
    for result in (component_scores(summary(), config), component_scores(summary(mean_asymmetry_percent=500, minimum_elbow_angle_deg=200, maximum_body_line_error_deg=100), config)):
        assert all(0 <= value <= 100 for value in result.values())

