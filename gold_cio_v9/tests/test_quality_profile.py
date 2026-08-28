from datetime import datetime, timedelta, timezone

from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.data.quality_profile import profile_minute_bars


def _bar(minute, volume=10.0):
    t = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minute)
    return HistoricalBar(
        instrument="GC", contract="GCG6", event_time=t,
        open=100.0, high=101.0, low=99.0, close=100.5, volume=volume,
        quality_state=QualityState.VERIFIED, source_id="TEST",
        roll_method=RollMethod.RAW_CONTRACT,
    )


def test_clean_profile_reports_identity_and_gap_metrics():
    p = profile_minute_bars([_bar(0), _bar(1), _bar(4), _bar(5, 0.0)])
    assert p.rows == 4
    assert p.unique_timestamps == 4
    assert p.clean_identity
    assert p.gap_count == 1
    assert p.max_gap_minutes == 2
    assert p.zero_volume_rows == 1
    assert p.negative_volume_rows == 0


def test_duplicates_and_non_monotonic_are_reported_not_repaired():
    p = profile_minute_bars([_bar(0), _bar(0), _bar(2), _bar(1)])
    assert p.duplicate_timestamps == 1
    assert p.non_monotonic_timestamps == 2
    assert not p.clean_identity


def test_negative_volume_is_reported():
    p = profile_minute_bars([_bar(0, -1.0)])
    assert p.negative_volume_rows == 1
