from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.validation.trust import PITObservation, PITViolation, assert_point_in_time, purge_training_indices


def t(minutes: int):
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minutes)


def test_explicit_future_source_dependency_raises():
    rows = [
        PITObservation(event_time=t(10), available_time=t(10), source_max_event_time=t(15)),
    ]
    with pytest.raises(PITViolation, match="PIT_FUTURE_SOURCE_DEPENDENCY"):
        assert_point_in_time(rows)


def test_available_time_before_event_raises():
    rows = [
        PITObservation(event_time=t(10), available_time=t(9), source_max_event_time=t(9)),
    ]
    with pytest.raises(PITViolation, match="PIT_AVAILABLE_BEFORE_EVENT"):
        assert_point_in_time(rows)


def test_label_horizon_overlap_is_purged():
    train = [
        (t(0), t(5)),
        (t(6), t(12)),  # overlaps test and must be purged
        (t(20), t(25)),
    ]
    test = [(t(10), t(15))]
    assert purge_training_indices(train, test) == [0, 2]


def test_boundary_touch_counts_as_overlap_and_is_purged():
    train = [(t(0), t(10)), (t(11), t(12))]
    test = [(t(10), t(11))]
    assert purge_training_indices(train, test) == []
