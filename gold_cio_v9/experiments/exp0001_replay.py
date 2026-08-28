"""Deterministic replay bridge for preregistered EXP-0001 setups.

This module performs no feature discovery and no threshold search. It consumes
point-in-time setup inputs that were constructed upstream, runs the locked signal
state machine, and emits immutable TradeCandidate objects for the backtest runner.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from gold_cio_v9.backtest.runner import TradeCandidate
from gold_cio_v9.experiments.exp0001_candidates import build_trade_candidate
from gold_cio_v9.experiments.exp0001_signal import FVGZone, TimedStructure, TimedSweep, generate_exp0001_signal
from gold_cio_v9.ict_engine.features import Bar


@dataclass(frozen=True)
class ReplaySetup:
    setup_id: str
    signal_index: int
    htf_location_ok: bool
    sweep: TimedSweep
    structure: TimedStructure
    zone: FVGZone
    retest_time: datetime
    retest_bar: Bar
    sweep_depth: float
    opposing_liquidity: float
    horizon_bars: int


def build_replay_candidates(setups: list[ReplaySetup]) -> tuple[TradeCandidate, ...]:
    """Convert PIT setup snapshots to candidates without repairing rejected setups.

    Invariants:
    - setup IDs must be unique;
    - signal indices must be strictly increasing in replay order;
    - a setup rejected by the locked signal state machine is skipped, not repaired;
    - candidate geometry is delegated to the locked candidate constructor.
    """
    seen_ids: set[str] = set()
    previous_index = -1
    candidates: list[TradeCandidate] = []

    for setup in setups:
        if not setup.setup_id:
            raise ValueError("setup_id must be non-empty")
        if setup.setup_id in seen_ids:
            raise ValueError("duplicate setup_id")
        seen_ids.add(setup.setup_id)
        if setup.signal_index <= previous_index:
            raise ValueError("signal_index must be strictly increasing")
        previous_index = setup.signal_index
        if setup.horizon_bars <= 0:
            raise ValueError("horizon_bars must be positive")

        signal = generate_exp0001_signal(
            htf_location_ok=setup.htf_location_ok,
            sweep=setup.sweep,
            structure=setup.structure,
            zone=setup.zone,
            retest_time=setup.retest_time,
            retest_bar=setup.retest_bar,
        )
        if signal is None:
            continue

        candidates.append(
            build_trade_candidate(
                signal=signal,
                signal_index=setup.signal_index,
                sweep_depth=setup.sweep_depth,
                opposing_liquidity=setup.opposing_liquidity,
                horizon_bars=setup.horizon_bars,
                candidate_id=setup.setup_id,
            )
        )

    return tuple(candidates)
