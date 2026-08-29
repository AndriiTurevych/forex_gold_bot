"""Trade-level causal evidence book for preregistered EXP-0001.

The evidence matrix is useful for completeness checks, but statistical validation
also needs the timestamp and contract identity of every resolved/ambiguous trade.
This module preserves those fields without adding any strategy logic or selection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Sequence

from gold_cio_v9.backtest.costs import CostAssumptions
from gold_cio_v9.data.governance import HistoricalBar
from gold_cio_v9.experiments.exp0001_evidence_matrix import (
    ATR_PERIOD,
    HORIZONS_MINUTES,
    POLICY_ID,
    SWING_LEFT_BARS,
    SWING_RIGHT_BARS,
    _EXPECTED_NO_EVIDENCE,
    split_raw_contract_segments,
)
from gold_cio_v9.experiments.exp0001_pipeline import PipelineConfig, run_exp0001_pipeline


@dataclass(frozen=True)
class EvidenceTrade:
    contract: str
    horizon_minutes: int
    candidate_id: str
    signal_time: datetime
    direction: str
    first_touch: str
    bars_to_first_touch: int | None
    net_pnl_price: float
    resolved: bool


@dataclass(frozen=True)
class EvidenceBookCell:
    contract: str
    horizon_minutes: int
    status: str
    context_points: int | None
    stream_events: int | None
    replay_setups: int | None
    trades: tuple[EvidenceTrade, ...]
    data_snapshot_hash: str | None
    candidate_snapshot_hash: str | None
    result_hash: str | None


@dataclass(frozen=True)
class EvidenceBook:
    policy_id: str
    contracts: tuple[str, ...]
    horizons_minutes: tuple[int, ...]
    cells: tuple[EvidenceBookCell, ...]

    def trades_for_horizon(self, horizon_minutes: int) -> tuple[EvidenceTrade, ...]:
        if horizon_minutes not in self.horizons_minutes:
            raise ValueError("horizon is not preregistered")
        rows = [t for cell in self.cells if cell.horizon_minutes == horizon_minutes for t in cell.trades]
        return tuple(sorted(rows, key=lambda t: (t.signal_time, t.contract, t.candidate_id)))


def build_exp0001_evidence_book(
    *,
    bars: Sequence[HistoricalBar],
    costs: CostAssumptions,
) -> EvidenceBook:
    """Run all contracts and all locked horizons and preserve every trade outcome."""
    segments = split_raw_contract_segments(bars)
    contracts = tuple(s[0].contract for s in segments)
    cells: list[EvidenceBookCell] = []

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
                cells.append(EvidenceBookCell(contract, horizon, status, None, None, None, (), None, None, None))
                continue

            trades: list[EvidenceTrade] = []
            for trade in result.backtest.trades:
                if trade.signal_index < 0 or trade.signal_index >= len(segment):
                    raise ValueError("backtest trade signal index is outside raw contract segment")
                bar = segment[trade.signal_index]
                if bar.contract != contract:
                    raise ValueError("trade contract identity mismatch")
                resolved = isfinite(trade.net_pnl_price) and trade.first_touch != "AMBIGUOUS"
                trades.append(EvidenceTrade(
                    contract=contract,
                    horizon_minutes=horizon,
                    candidate_id=trade.candidate_id,
                    signal_time=bar.event_time,
                    direction=trade.direction,
                    first_touch=trade.first_touch,
                    bars_to_first_touch=trade.bars_to_first_touch,
                    net_pnl_price=trade.net_pnl_price,
                    resolved=resolved,
                ))
            cells.append(EvidenceBookCell(
                contract=contract,
                horizon_minutes=horizon,
                status="OK",
                context_points=result.context_points,
                stream_events=result.stream_events,
                replay_setups=result.replay_setups,
                trades=tuple(trades),
                data_snapshot_hash=result.backtest.data_snapshot_hash,
                candidate_snapshot_hash=result.backtest.candidate_snapshot_hash,
                result_hash=result.backtest.result_hash,
            ))

    expected = len(segments) * len(HORIZONS_MINUTES)
    if len(cells) != expected:
        raise RuntimeError("evidence book is incomplete")
    return EvidenceBook(POLICY_ID, contracts, HORIZONS_MINUTES, tuple(cells))
