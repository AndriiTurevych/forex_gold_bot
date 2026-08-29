"""End-to-end deterministic replay entry point for EXP-0001.

Bridges point-in-time replay setups to the strategy-agnostic backtest runner while
enforcing bar/setup alignment and raw GC contract-boundary integrity. It performs
no parameter search and no setup repair.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Sequence

from gold_cio_v9.backtest.costs import CostAssumptions
from gold_cio_v9.backtest.runner import BacktestResult, TradeCandidate, run_backtest
from gold_cio_v9.data.governance import HistoricalBar, require_dataset_ready
from gold_cio_v9.experiments.exp0001_replay import ReplaySetup, build_replay_candidates


def _validate_time_order(bars: Sequence[HistoricalBar]) -> None:
    if any(bars[i].event_time >= bars[i + 1].event_time for i in range(len(bars) - 1)):
        raise ValueError("historical bars must be strictly time ordered with unique timestamps")


def _validate_setup_alignment(bars: Sequence[HistoricalBar], setups: Sequence[ReplaySetup]) -> None:
    n = len(bars)
    for setup in setups:
        if setup.signal_index < 0 or setup.signal_index >= n:
            raise ValueError(f"setup {setup.setup_id} signal_index is outside dataset")
        bar = bars[setup.signal_index]
        if bar.event_time != setup.retest_time:
            raise ValueError(f"setup {setup.setup_id} retest_time does not match signal_index bar")
        rb = setup.retest_bar
        if (bar.open, bar.high, bar.low, bar.close) != (rb.open, rb.high, rb.low, rb.close):
            raise ValueError(f"setup {setup.setup_id} retest_bar does not match authoritative historical bar")


def _candidate_future(
    bars: Sequence[HistoricalBar], candidate: TradeCandidate
) -> Sequence[HistoricalBar]:
    if candidate.horizon_minutes is not None:
        cutoff = bars[candidate.signal_index].event_time + timedelta(minutes=candidate.horizon_minutes)
        return [b for b in bars[candidate.signal_index + 1 :] if b.event_time <= cutoff]
    end = min(len(bars), candidate.signal_index + 1 + candidate.horizon_bars)
    return bars[candidate.signal_index + 1 : end]


def _validate_candidate_contract_horizons(
    bars: Sequence[HistoricalBar], candidates: Sequence[TradeCandidate]
) -> None:
    """Prevent outcome labels from crossing a raw futures contract boundary."""
    for candidate in candidates:
        start_contract = bars[candidate.signal_index].contract
        future = _candidate_future(bars, candidate)
        if any(b.contract != start_contract for b in future):
            raise ValueError(f"candidate {candidate.candidate_id} horizon crosses contract boundary")


def run_exp0001_backtest(
    *,
    bars: Sequence[HistoricalBar],
    setups: Sequence[ReplaySetup],
    costs: CostAssumptions,
) -> BacktestResult:
    """Run one causal EXP-0001 replay on authoritative raw GC bars."""
    materialized = list(bars)
    require_dataset_ready(materialized, instrument="GC")
    _validate_time_order(materialized)
    if not setups:
        raise ValueError("no replay setups supplied")
    _validate_setup_alignment(materialized, setups)
    candidates = build_replay_candidates(list(setups))
    if not candidates:
        raise ValueError("no accepted EXP-0001 candidates after locked signal gate")
    _validate_candidate_contract_horizons(materialized, candidates)
    return run_backtest(bars=materialized, candidates=candidates, instrument="GC", costs=costs)
