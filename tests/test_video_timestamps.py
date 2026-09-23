import pytest

from uliana.video_timestamps import increasing_timestamp_ms


def test_container_timestamp_and_monotonic_adjustment():
    assert increasing_timestamp_ms(123.4, 3, 30, None) == (123, "container_timestamp")
    timestamp, source = increasing_timestamp_ms(123.4, 4, 30, 123)
    assert timestamp == 124 and source.endswith("monotonic_adjustment")


def test_timestamp_fallback_and_invalid_input():
    assert increasing_timestamp_ms(None, 3, 30, None) == (100, "frame_index_fps_fallback")
    with pytest.raises(ValueError): increasing_timestamp_ms(None, 3, 0, None)

