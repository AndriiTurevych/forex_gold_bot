from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.experiments.exp0001_inputs import DirectionalPermission, build_exp0001_causal_inputs


def _bars(values):
    t0 = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    out = []
    for i, (o, h, l, c) in enumerate(values):
        out.append(HistoricalBar(
            instrument="GC", contract="GCG6", event_time=t0 + timedelta(minutes=i),
            open=o, high=h, low=l, close=c, volume=10.0,
            quality_state=QualityState.VERIFIED, source_id="TEST",
            roll_method=RollMethod.RAW_CONTRACT,
        ))
    return out


def test_directional_permission_is_explicit():
    p = DirectionalPermission(True, False)
    assert p.allows("LONG") is True
    assert p.allows("SHORT") is False
    with pytest.raises(ValueError, match="invalid direction"):
        p.allows("FLAT")


def test_prior_day_midpoint_permission_uses_completed_day_only():
    # Two UTC days. Day 1 range midpoint is 100. Day 2 close 95 -> LONG only.
    values = []
    t0 = datetime(2026, 1, 5, 23, 55, tzinfo=timezone.utc)
    for i, c in enumerate([100, 110, 90, 100, 100, 95]):
        values.append(HistoricalBar(
            instrument="GC", contract="GCG6", event_time=t0 + timedelta(minutes=i),
            open=c, high=c + 1, low=c - 1, close=c, volume=10.0,
            quality_state=QualityState.VERIFIED, source_id="TEST",
            roll_method=RollMethod.RAW_CONTRACT,
        ))
    state = build_exp0001_causal_inputs(values, atr_period=1, swing_left_bars=1, swing_right_bars=1)
    day2_idx = 5
    assert state.htf_permission_by_index[day2_idx].long is True
    assert state.htf_permission_by_index[day2_idx].short is False
    assert 0 not in state.htf_permission_by_index


def test_current_bar_cannot_rewrite_its_prior_day_permission():
    t0 = datetime(2026, 1, 5, 23, 57, tzinfo=timezone.utc)
    bars = [
        HistoricalBar(instrument="GC", contract="GCG6", event_time=t0, open=100, high=101, low=99, close=100, volume=10, quality_state=QualityState.VERIFIED, source_id="TEST", roll_method=RollMethod.RAW_CONTRACT),
        HistoricalBar(instrument="GC", contract="GCG6", event_time=t0 + timedelta(minutes=1), open=100, high=111, low=89, close=100, volume=10, quality_state=QualityState.VERIFIED, source_id="TEST", roll_method=RollMethod.RAW_CONTRACT),
        HistoricalBar(instrument="GC", contract="GCG6", event_time=t0 + timedelta(minutes=2), open=100, high=101, low=99, close=100, volume=10, quality_state=QualityState.VERIFIED, source_id="TEST", roll_method=RollMethod.RAW_CONTRACT),
        HistoricalBar(instrument="GC", contract="GCG6", event_time=t0 + timedelta(minutes=3), open=95, high=1000, low=1, close=95, volume=10, quality_state=QualityState.VERIFIED, source_id="TEST", roll_method=RollMethod.RAW_CONTRACT),
    ]
    state = build_exp0001_causal_inputs(bars, atr_period=1, swing_left_bars=1, swing_right_bars=1)
    p = state.htf_permission_by_index[3]
    assert p.long is True and p.short is False


def test_trend_requires_two_confirmed_highs_and_lows():
    values = [
        (100,101,99,100), (102,103,101,102), (100,101,98,99),
        (104,105,103,104), (102,103,100,101), (106,107,105,106),
        (104,105,102,103), (108,109,107,108), (106,107,104,105),
    ]
    state = build_exp0001_causal_inputs(_bars(values), atr_period=1, swing_left_bars=1, swing_right_bars=1)
    assert 2 not in state.prior_trend_by_index
    assert any(v == "BULLISH" for v in state.prior_trend_by_index.values())


def test_mixed_contract_fails_via_causal_context():
    bars = _bars([(100,101,99,100), (101,102,100,101), (100,101,99,100)])
    bars[1] = HistoricalBar(
        instrument="GC", contract="GCJ6", event_time=bars[1].event_time,
        open=101, high=102, low=100, close=101, volume=10,
        quality_state=QualityState.VERIFIED, source_id="TEST", roll_method=RollMethod.RAW_CONTRACT,
    )
    with pytest.raises(ValueError, match="single contract"):
        build_exp0001_causal_inputs(bars, atr_period=1, swing_left_bars=1, swing_right_bars=1)
