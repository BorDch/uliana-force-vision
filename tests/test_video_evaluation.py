from uliana.video_evaluation import match_events


def test_event_matching_is_one_to_one():
    matches = match_events([1.0, 2.0], [.9, 1.1, 2.2], .25)
    assert len(matches) == 2
    assert len({match.detection_index for match in matches}) == 2

