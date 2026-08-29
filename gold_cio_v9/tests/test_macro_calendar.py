from datetime import date, datetime, timezone

import pytest

from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.validation.exp0001_regimes import MacroEvent
from gold_cio_v9.validation.macro_calendar import build_macro_calendar_snapshot, validate_macro_calendar_for_bars


def _bar(day):
    return HistoricalBar(
        instrument="GC", contract="GCQ5", event_time=datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc),
        open=100, high=101, low=99, close=100, volume=1,
        quality_state=QualityState.VERIFIED, source_id="TEST", roll_method=RollMethod.RAW_CONTRACT,
    )


def test_hash_is_deterministic_and_order_independent():
    a = MacroEvent(datetime(2025, 6, 4, 12, tzinfo=timezone.utc), datetime(2025, 6, 1, tzinfo=timezone.utc), "CPI")
    b = MacroEvent(datetime(2025, 6, 6, 12, tzinfo=timezone.utc), datetime(2025, 6, 1, tzinfo=timezone.utc), "NFP")
    x = build_macro_calendar_snapshot(coverage_start=date(2025, 6, 1), coverage_end=date(2025, 6, 30), source_id="calendar:v1", events=(a, b))
    y = build_macro_calendar_snapshot(coverage_start=date(2025, 6, 1), coverage_end=date(2025, 6, 30), source_id="calendar:v1", events=(b, a))
    assert x.calendar_hash == y.calendar_hash


def test_full_bar_coverage_is_required():
    snap = build_macro_calendar_snapshot(coverage_start=date(2025, 6, 2), coverage_end=date(2025, 6, 2), source_id="calendar:v1", events=())
    with pytest.raises(ValueError, match="does not cover"):
        validate_macro_calendar_for_bars(snap, (_bar(date(2025, 6, 2)), _bar(date(2025, 6, 3))))


def test_event_outside_declared_coverage_is_rejected():
    event = MacroEvent(datetime(2025, 7, 1, 12, tzinfo=timezone.utc), datetime(2025, 6, 1, tzinfo=timezone.utc), "CPI")
    with pytest.raises(ValueError, match="outside declared"):
        build_macro_calendar_snapshot(coverage_start=date(2025, 6, 1), coverage_end=date(2025, 6, 30), source_id="calendar:v1", events=(event,))


def test_duplicate_event_identity_is_rejected():
    e1 = MacroEvent(datetime(2025, 6, 4, 12, tzinfo=timezone.utc), datetime(2025, 6, 1, tzinfo=timezone.utc), "CPI")
    e2 = MacroEvent(datetime(2025, 6, 4, 12, tzinfo=timezone.utc), datetime(2025, 6, 2, tzinfo=timezone.utc), "CPI")
    with pytest.raises(ValueError, match="duplicate macro event"):
        build_macro_calendar_snapshot(coverage_start=date(2025, 6, 1), coverage_end=date(2025, 6, 30), source_id="calendar:v1", events=(e1, e2))
