from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.ict_engine.causal_context import build_causal_context, confirm_swings


def _bar(i, *, high, low, close=None, day=0, contract="GCZ5", roll=False):
    base = datetime(2025, 10, 1 + day, 13, 0, tzinfo=timezone.utc)
    c = (high + low) / 2 if close is None else close
    return HistoricalBar(
        instrument="GC", contract=contract, event_time=base + timedelta(minutes=i),
        open=c, high=high, low=low, close=c, volume=10.0,
        quality_state=QualityState.VERIFIED, source_id="TEST",
        roll_method=RollMethod.RAW_CONTRACT, is_roll_window=roll,
    )


def test_swing_is_not_visible_before_confirmation_bar():
    bars = [
        _bar(0, high=10, low=8),
        _bar(1, high=12, low=9),
        _bar(2, high=15, low=10),
        _bar(3, high=13, low=9),
        _bar(4, high=11, low=8),
    ]
    swings = confirm_swings(bars, left_bars=2, right_bars=2)
    high = next(s for s in swings if s.kind == "HIGH")
    assert high.event_time == bars[2].event_time
    assert high.available_time == bars[4].event_time

    ctx = build_causal_context(bars, atr_period=1, swing_left_bars=2, swing_right_bars=2)
    assert ctx[3].latest_swing_high is None
    assert ctx[4].latest_swing_high == high


def test_prior_day_levels_appear_only_on_next_trading_day():
    bars = [
        _bar(0, high=11, low=8, day=0),
        _bar(1, high=14, low=9, day=0),
        _bar(0, high=20, low=17, day=1),
        _bar(1, high=21, low=18, day=1),
    ]
    ctx = build_causal_context(bars, atr_period=1, swing_left_bars=1, swing_right_bars=1)
    assert ctx[0].prior_day_high is None
    assert ctx[1].prior_day_low is None
    assert ctx[2].prior_day_high == 14
    assert ctx[2].prior_day_low == 8
    assert ctx[3].prior_day_high == 14


def test_atr_uses_only_bars_strictly_before_decision_bar():
    bars = [
        _bar(0, high=12, low=10, close=11),
        _bar(1, high=15, low=11, close=14),
        _bar(2, high=30, low=5, close=20),
    ]
    ctx = build_causal_context(bars, atr_period=1, swing_left_bars=1, swing_right_bars=1)
    assert ctx[0].atr_prior is None
    assert ctx[1].atr_prior == 2
    # At bar 2, ATR uses bar 1 TR against bar 0 close = max(4,4,0)=4;
    # the huge current bar cannot contaminate its own normalization.
    assert ctx[2].atr_prior == 4


def test_mixed_contract_or_roll_window_fails_closed():
    mixed = [_bar(0, high=10, low=8), _bar(1, high=11, low=9, contract="GCG6")]
    with pytest.raises(ValueError, match="one contract"):
        build_causal_context(mixed, atr_period=1, swing_left_bars=1, swing_right_bars=1)

    with pytest.raises(ValueError, match="roll-window"):
        build_causal_context([_bar(0, high=10, low=8, roll=True)], atr_period=1, swing_left_bars=1, swing_right_bars=1)


def test_non_chronological_bars_fail_closed():
    a = _bar(1, high=10, low=8)
    b = _bar(0, high=11, low=9)
    with pytest.raises(ValueError, match="chronological"):
        confirm_swings([a, b], left_bars=1, right_bars=1)
