from uliana.synchronization import synchronize
from uliana.types import ForceSample, PoseSample


def test_matches_inside_and_rejects_outside_window():
    poses = [PoseSample(100, 160, 2, .9), PoseSample(300, 90, 2, .9)]
    forces = [ForceSample(140, 100, 100), ForceSample(400, 100, 100)]
    result, stats = synchronize(poses, forces, 50)
    assert result[0].force is forces[0]
    assert result[1].force is None
    assert stats["missing_matches"] == 1


def test_delayed_stream_is_explicitly_unmatched():
    poses = [PoseSample(t, 160, 2, .9) for t in (0, 33, 66)]
    forces = [ForceSample(t + 200, 100, 100) for t in (0, 20, 40)]
    result, stats = synchronize(poses, forces, 50)
    assert all(sample.force is None for sample in result)
    assert stats["matched"] == 0
