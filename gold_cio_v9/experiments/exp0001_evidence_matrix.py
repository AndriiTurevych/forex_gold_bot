"""Precommitted multi-contract evidence matrix for EXP-0001.

Runs every raw GC contract segment across every preregistered wall-clock horizon
[5, 15, 30, 60]. No horizon is selected or ranked inside this module. Contracts
with no causal setup are recorded explicitly rather than silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from gold_cio_v9.backtest.costs import CostAssumptions
from gold_cio_v9.data.governance import HistoricalBar
from gold_cio_v9.experiments.exp0001_locked import (
    ATR_PERIOD,
    HORIZONS_MINUTES,
    IMPLEMENTATION_POLICY_ID,
    SWING_LEFT_BARS,
    SWING_RIGHT_BARS,
)
from gold_cio_v9.experiments.exp0001_pipeline import PipelineConfig, run_exp0001_pipeline

POLICY_ID = IMPLEMENTATION_POLICY_ID

_EXPECTED_NO_EVIDENCE = {
    "no complete point-in-time context available": "NO_CONTEXT",
    "no causal EXP-0001 events available": "NO_EVENTS",
    "no complete causal EXP-0001 replay setups": "NO_SETUPS",
    "no accepted EXP-0001 candidates after locked signal gate": "NO_ACCEPTED_CANDIDATES",
}


@dataclass(frozen=True)
class EvidenceMatrixRow:
    contract: str
    horizon_minutes: int
    status: str
    context_points: int | None
    stream_events: int | None
    replay_setups: int | None
    trade_count: int
    result_hash: str | None


@dataclass(frozen=True)
class EvidenceMatrixResult:
    policy_id: str
    contracts: tuple[str, ...]
    horizons_minutes: tuple[int, ...]
    rows: tuple[EvidenceMatrixRow, ...]


def split_raw_contract_segments(bars: Sequence[HistoricalBar]) -> tuple[tuple[HistoricalBar, ...], ...]:
    if not bars:
        raise ValueError("bars are required")
    segments: list[list[HistoricalBar]] = []
    seen: set[str] = set()
    current: str | None = None
    for bar in bars:
        if bar.instrument != "GC" or not bar.contract:
            raise ValueError("matrix requires explicit GC contract bars")
        if current != bar.contract:
            if bar.contract in seen:
                raise ValueError("contract re-entry in evidence dataset")
            seen.add(bar.contract)
            segments.append([])
            current = bar.contract
        if not bar.is_roll_window:
            segments[-1].append(bar)
    if any(not segment for segment in segments):
        raise ValueError("contract segment contains only roll-window bars")
    return tuple(tuple(s) for s in segments)


def run_exp0001_evidence_matrix(*, bars: Sequence[HistoricalBar], costs: CostAssumptions) -> EvidenceMatrixResult:
    segments = split_raw_contract_segments(bars)
    contracts = tuple(s[0].contract for s in segments)
    rows: list[EvidenceMatrixRow] = []
    for segment in segments:
        contract = segment[0].contract
        assert contract is not None
        for horizon in HORIZONS_MINUTES:
            cfg = PipelineConfig(ATR_PERIOD, SWING_LEFT_BARS, SWING_RIGHT_BARS, horizon)
            try:
                result = run_exp0001_pipeline(bars=segment, config=cfg, costs=costs)
            except ValueError as exc:
                status = _EXPECTED_NO_EVIDENCE.get(str(exc))
                if status is None:
                    raise
                rows.append(EvidenceMatrixRow(contract, horizon, status, None, None, None, 0, None))
                continue
            rows.append(EvidenceMatrixRow(
                contract=contract, horizon_minutes=horizon, status="OK",
                context_points=result.context_points, stream_events=result.stream_events,
                replay_setups=result.replay_setups, trade_count=len(result.backtest.trades),
                result_hash=result.backtest.result_hash,
            ))
    expected = len(segments) * len(HORIZONS_MINUTES)
    if len(rows) != expected:
        raise RuntimeError("evidence matrix is incomplete")
    return EvidenceMatrixResult(POLICY_ID, contracts, HORIZONS_MINUTES, tuple(rows))
