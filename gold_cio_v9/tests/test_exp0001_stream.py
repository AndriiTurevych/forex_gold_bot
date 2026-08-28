from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.experiments.exp0001_stream import ContextPoint, build_event_stream


def _bar(i, o, h, l, c, *, roll=False):
    return HistoricalBar(
        instrument="GC",
        contract="GCZ5",
        event_time=datetime(2025, 10, 1, tzinfo=timezone.utc) + timedelta(minutes=i),
        open=o, high=h, low=l, close=c, volume=10,
        quality_state=QualityState.VERIFIED,
        source_id="TEST",
        roll_method=RollMethod.RAW_CONTRACT,
        is_roll_window=roll,
    )


def _ctx(i, *, trend="BEARISH", atr=1.0):
    return ContextPoint(
        index=i,
        reference_high=101.0,
        reference_low=99.0,
        prior_swing_high=101.0,
        prior_swing_low=99.0,
        prior_trend=trend,
        atr=atr,
    )


def test_emits_only_from_available_context_and_closed_bars():
    bars = [
        _bar(0, 100.0, 100.5, 99.5, 100.2),
        _bar(1, 100.2, 100.8, 100.0, 100.6),
        _bar(2, 100.6, 102.2, 100.5, 102.0),
    ]
    events = build_event_stream(bars, [_ctx(2)])
    assert len(events) == 1
    assert events[0].index == 2
    assert events[0].structure is not None
    assert events[0].structure.event.event_time if hasattr(events[0].structure.event, "event_time") else True


def test_fvg_is_only_available_on_third_candle_close():
    bars = [
        _bar(0, 100.0, 100.5, 99.5, 100.0),
        _bar(1, 100.2, 101.0, 100.1, 100.8),
        _bar(2, 101.2, 102.0, 101.1, 101.8),
    ]
    events = build_event_stream(bars, [_ctx(1), _ctx(2)])
    e1, e2 = events
    assert e1.bullish_fvg is None
    assert e2.bullish_fvg is not None
    assert e2.bullish_fvg.event_time == bars[2].event_time


def test_roll_window_bar_emits_no_event():
    bars = [
        _bar(0, 100, 100.5, 99.5, 100),
        _bar(1, 100, 101.5, 99.5, 101.2, roll=True),
    ]
    assert build_event_stream(bars, [_ctx(1)]) == ()


def test_non_monotonic_bars_fail_closed():
    b0 = _bar(0, 100, 101, 99, 100)
    b1 = HistoricalBar(**{**b0.__dict__, "open": 100.1, "high": 101.1, "low": 99.1, "close": 100.1})
    with pytest.raises(ValueError, match="strictly increasing"):
        build_event_stream([b0, b1], [_ctx(1)])


def test_duplicate_context_indices_fail_closed():
    bars = [_bar(0, 100, 101, 99, 100), _bar(1, 100, 101, 99, 100)]
    with pytest.raises(ValueError, match="context indices"):
        build_event_stream(bars, [_ctx(1), _ctx(1)])


def test_context_out_of_range_fails_closed():
    bars = [_bar(0, 100, 101, 99, 100)]
    with pytest.raises(ValueError, match="out of range"):
        build_event_stream(bars, [_ctx(5)])
