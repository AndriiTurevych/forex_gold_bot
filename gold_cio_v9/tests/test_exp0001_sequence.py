from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.experiments.exp0001_sequence import assemble_replay_setups
from gold_cio_v9.experiments.exp0001_signal import FVGZone, TimedStructure, TimedSweep
from gold_cio_v9.experiments.exp0001_stream import ContextPoint, StreamEvent
from gold_cio_v9.ict_engine.features import Sweep
from gold_cio_v9.ict_engine.structure import StructureEvent


def _bar(i, close=100.0, low=99.0, high=101.0, contract="GCZ5", roll=False):
    t = datetime(2025, 10, 1, tzinfo=timezone.utc) + timedelta(minutes=i)
    return HistoricalBar(
        instrument="GC", contract=contract, event_time=t,
        open=close, high=high, low=low, close=close, volume=10.0,
        quality_state=QualityState.VERIFIED, source_id="TEST",
        roll_method=RollMethod.RAW_CONTRACT, is_roll_window=roll,
    )


def _ctx(i):
    return ContextPoint(i, 110.0, 90.0, 105.0, 95.0, "BEARISH", 2.0)


def _long_events(bars):
    return [
        StreamEvent(1, TimedSweep(bars[1].event_time, Sweep("SSL", 90.0, 1.0)), None, None, None),
        StreamEvent(2, None, TimedStructure(bars[2].event_time, StructureEvent("MSS", "BULLISH", 105.0, 106.0, 1.0)), None, None),
        StreamEvent(3, None, None, FVGZone(bars[3].event_time, 100.0, 102.0, "BULLISH"), None),
        StreamEvent(4, None, None, None, None),
    ]


def test_full_sequence_emits_replay_setup_on_first_later_retest():
    bars = [_bar(0), _bar(1, low=89.0), _bar(2, close=106.0, low=100.0, high=107.0),
            _bar(3, close=103.0, low=102.5, high=104.0), _bar(4, close=101.0, low=100.5, high=102.5)]
    setups = assemble_replay_setups(
        bars=bars, events=_long_events(bars), context=[_ctx(i) for i in range(5)],
        htf_permission={4: True}, horizon_bars=60,
    )
    assert len(setups) == 1
    s = setups[0]
    assert s.signal_index == 4
    assert s.htf_location_ok is True
    assert s.opposing_liquidity == 110.0
    assert s.sweep_depth == 1.0


def test_fvg_same_bar_is_not_treated_as_retest():
    bars = [_bar(0), _bar(1, low=89.0), _bar(2), _bar(3, close=101.0, low=100.5, high=102.0)]
    setups = assemble_replay_setups(
        bars=bars, events=_long_events(bars)[:3], context=[_ctx(i) for i in range(4)],
        htf_permission={3: True}, horizon_bars=60,
    )
    assert setups == ()


def test_roll_window_clears_pending_sequence():
    bars = [_bar(0), _bar(1, low=89.0), _bar(2), _bar(3, roll=True), _bar(4, close=101.0, low=100.5, high=102.0)]
    events = _long_events(bars)
    setups = assemble_replay_setups(
        bars=bars, events=events, context=[_ctx(i) for i in range(5)],
        htf_permission={4: True}, horizon_bars=60,
    )
    assert setups == ()


def test_missing_context_for_event_fails_closed():
    bars = [_bar(0), _bar(1, low=89.0)]
    events = [StreamEvent(1, TimedSweep(bars[1].event_time, Sweep("SSL", 90.0, 1.0)), None, None, None)]
    with pytest.raises(ValueError, match="missing contemporaneous context"):
        assemble_replay_setups(
            bars=bars, events=events, context=[_ctx(0)],
            htf_permission={}, horizon_bars=60,
        )


def test_nonpositive_horizon_fails_closed():
    with pytest.raises(ValueError, match="horizon_bars"):
        assemble_replay_setups(bars=[_bar(0)], events=[], context=[_ctx(0)], htf_permission={}, horizon_bars=0)
