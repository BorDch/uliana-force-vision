from uliana.reliability import assess
from uliana.baselines import camera_only
from uliana.scoring import decide
from uliana.types import ForceSample, PoseSample, RepetitionSummary, SynchronizedSample


def make_samples(confidence=.9, force=200, valid=True):
    return [SynchronizedSample(PoseSample(i * 34, 90, 3, confidence), ForceSample(i * 34, force, 180, valid), 0) for i in range(20)]


def make_summary(left=240, right=160):
    return RepetitionSummary(1, left, right, 20, 20, 100, 80, 92, 3, .9)


def test_low_pose_confidence_abstains(config):
    state = assess(make_samples(confidence=.4), config)
    decision = decide(make_summary(), state, config)
    assert decision.abstained and "camera" in decision.cue.lower()


def test_missing_and_saturated_force_abstain(config):
    missing = [SynchronizedSample(PoseSample(i, 90, 2, .9), None, None) for i in range(10)]
    assert decide(make_summary(), assess(missing, config), config).abstained
    saturated = make_samples(force=700, valid=False)
    assert decide(make_summary(), assess(saturated, config), config).abstained


def test_missing_force_does_not_invalidate_camera_only(config):
    missing = [SynchronizedSample(PoseSample(i, 90, 2, .9), None, None) for i in range(10)]
    reliability = assess(missing, config)
    assert not reliability.force_reliable and reliability.pose_reliable
    assert not camera_only(make_summary(left=200, right=200), reliability, config).abstained


def test_feedback_direction(config):
    reliable = assess(make_samples(), config)
    assert decide(make_summary(240, 160), reliable, config).cue == "Shift weight right."
    assert decide(make_summary(160, 240), reliable, config).cue == "Shift weight left."
