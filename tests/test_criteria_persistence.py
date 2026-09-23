import pytest
from dataclasses import replace
from test_five_camera_criteria import features, CONFIG, assess_hand_placement


from uliana.fusion.criteria_v2 import _persistent_fraction


def test_missing_frames_do_not_bridge_persistence():
    fraction, longest = _persistent_fraction([(0,True),(50,True),(650,True),(700,True)],250)
    assert longest == 50
    assert fraction == pytest.approx(100/700)


def test_one_sided_hand_offset_is_not_averaged_away():
    item = features()
    item = replace(item,hand_placement_data=[(t,.5,0,mid) for t,_,_,mid in item.hand_placement_data])
    assert assess_hand_placement(item,.9,CONFIG).result == "condition_detected"
