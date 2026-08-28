from datetime import datetime, timezone

import pytest

from gold_cio_v9.experiments.exp0001_events import TimedBar, extract_fvg, extract_mss, extract_sweep
from gold_cio_v9.ict_engine.features import Bar


def tb(minute, o, h, l, c):
    ts = datetime(2026, 1, 2, 14, minute, tzinfo=timezone.utc)
    return TimedBar(ts, Bar(ts.isoformat(), o, h, l, c))


def test_extract_ssl_sweep_at_closed_bar_time():
    e = extract_sweep(tb(1, 100, 101, 97, 100), reference_high=105, reference_low=98)
    assert e is not None
    assert e.sweep.side == "SSL"
    assert e.event_time.minute == 1


def test_two_sided_sweep_is_rejected():
    e = extract_sweep(tb(1, 100, 106, 97, 100), reference_high=105, reference_low=98)
    assert e is None


def test_mss_requires_displacement_and_opposing_break():
    e = extract_mss(
        tb(2, 99, 103, 99, 102),
        prior_swing_high=101,
        prior_swing_low=97,
        prior_trend="BEARISH",
        atr=2.0,
    )
    assert e is not None
    assert e.event.kind == "MSS"
    assert e.event.direction == "BULLISH"


def test_weak_opposing_break_is_not_mss():
    e = extract_mss(
        tb(2, 100.4, 101.2, 100.2, 101.1),
        prior_swing_high=101,
        prior_swing_low=97,
        prior_trend="BEARISH",
        atr=2.0,
    )
    assert e is None


def test_bullish_fvg_available_only_at_third_close():
    first = tb(3, 100, 101, 99, 100.5)
    middle = tb(4, 101, 103, 100.8, 102.5)
    third = tb(5, 102, 104, 101.5, 103)
    z = extract_fvg(first, middle, third, direction="BULLISH")
    assert z is not None
    assert z.low == 101
    assert z.high == 101.5
    assert z.event_time == third.event_time


def test_fvg_rejects_non_monotonic_time():
    with pytest.raises(ValueError):
        extract_fvg(tb(4, 100, 101, 99, 100), tb(3, 100, 101, 99, 100), tb(5, 102, 103, 102, 103), direction="BULLISH")
