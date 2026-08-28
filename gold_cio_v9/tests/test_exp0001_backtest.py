from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.backtest.costs import CostAssumptions
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.experiments.exp0001_backtest import run_exp0001_backtest
from gold_cio_v9.experiments.exp0001_replay import ReplaySetup
from gold_cio_v9.experiments.exp0001_signal import FVGZone, TimedStructure, TimedSweep
from gold_cio_v9.ict_engine.features import Bar, Sweep
from gold_cio_v9.ict_engine.structure import StructureEvent


def _hbar(i: int, *, contract="GCG6", close=None):
    t = datetime(2026, 1, 1, 13, 20, tzinfo=timezone.utc) + timedelta(minutes=i)
    c = 102.0 if close is None else close
    return HistoricalBar(
        instrument="GC",
        contract=contract,
        event_time=t,
        open=c,
        high=c + 1.0,
        low=c - 1.0,
        close=c,
        volume=100.0,
        quality_state=QualityState.VERIFIED,
        source_id="TEST",
        roll_method=RollMethod.RAW_CONTRACT,
    )


def _setup(index=10, *, setup_id="s1", htf=True, horizon=3):
    t0 = datetime(2026, 1, 1, 13, 27, tzinfo=timezone.utc)
    return ReplaySetup(
        setup_id=setup_id,
        signal_index=index,
        htf_location_ok=htf,
        sweep=TimedSweep(t0, Sweep("SSL", 100.0, 1.0)),
        structure=TimedStructure(
            t0 + timedelta(minutes=1),
            StructureEvent("MSS", "BULLISH", 101.0, 102.0, 1.0),
        ),
        zone=FVGZone(t0 + timedelta(minutes=2), 101.0, 102.0, "BULLISH"),
        retest_time=t0 + timedelta(minutes=3),
        retest_bar=Bar("2026-01-01T13:30:00Z", 102.0, 103.0, 101.0, 102.0),
        sweep_depth=1.0,
        opposing_liquidity=106.0,
        horizon_bars=horizon,
    )


def _bars():
    bars = [_hbar(i) for i in range(15)]
    # authoritative bar at signal index must exactly match replay snapshot
    bars[10] = HistoricalBar(
        instrument="GC", contract="GCG6", event_time=datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc),
        open=102.0, high=103.0, low=101.0, close=102.0, volume=100.0,
        quality_state=QualityState.VERIFIED, source_id="TEST", roll_method=RollMethod.RAW_CONTRACT,
    )
    # target is hit on first future bar
    bars[11] = HistoricalBar(
        instrument="GC", contract="GCG6", event_time=datetime(2026, 1, 1, 13, 31, tzinfo=timezone.utc),
        open=103.0, high=106.5, low=102.5, close=106.0, volume=100.0,
        quality_state=QualityState.VERIFIED, source_id="TEST", roll_method=RollMethod.RAW_CONTRACT,
    )
    return bars


def _costs():
    return CostAssumptions(0.1, 0.02, 0.04)


def test_full_replay_produces_backtest_result():
    result = run_exp0001_backtest(bars=_bars(), setups=[_setup()], costs=_costs())
    assert result.instrument == "GC"
    assert len(result.trades) == 1
    assert result.trades[0].candidate_id == "s1"
    assert result.trades[0].first_touch == "TARGET"
    assert result.trades[0].net_pnl_price < result.trades[0].gross_pnl_price


def test_retest_timestamp_mismatch_fails_closed():
    bad = _setup()
    bad = ReplaySetup(**{**bad.__dict__, "retest_time": bad.retest_time + timedelta(minutes=1)})
    with pytest.raises(ValueError, match="retest_time"):
        run_exp0001_backtest(bars=_bars(), setups=[bad], costs=_costs())


def test_retest_ohlc_mismatch_fails_closed():
    bad = _setup()
    bad = ReplaySetup(**{**bad.__dict__, "retest_bar": Bar("x", 102.0, 104.0, 101.0, 102.0)})
    with pytest.raises(ValueError, match="retest_bar"):
        run_exp0001_backtest(bars=_bars(), setups=[bad], costs=_costs())


def test_duplicate_or_unsorted_timestamps_fail_closed():
    bars = _bars()
    bars[12] = HistoricalBar(**{**bars[12].__dict__, "event_time": bars[11].event_time})
    with pytest.raises(ValueError, match="strictly time ordered"):
        run_exp0001_backtest(bars=bars, setups=[_setup()], costs=_costs())


def test_candidate_cannot_cross_contract_boundary():
    bars = _bars()
    bars[12] = HistoricalBar(**{**bars[12].__dict__, "contract": "GCJ6"})
    with pytest.raises(ValueError, match="crosses contract boundary"):
        run_exp0001_backtest(bars=bars, setups=[_setup(horizon=3)], costs=_costs())


def test_all_rejected_setups_fail_closed_not_silent_empty_run():
    with pytest.raises(ValueError, match="no accepted"):
        run_exp0001_backtest(bars=_bars(), setups=[_setup(htf=False)], costs=_costs())
