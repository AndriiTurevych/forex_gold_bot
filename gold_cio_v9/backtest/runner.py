"""Deterministic production backtest runner core for Gold CIO v9.

This module is deliberately strategy-agnostic. Alpha logic produces immutable
TradeCandidate objects; the runner validates the dataset, applies costs, produces
trade outcomes and hashes every material input/output for evidence lineage.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import isfinite
from typing import Iterable, Literal, Sequence

from gold_cio_v9.backtest.costs import CostAssumptions, net_pnl_price
from gold_cio_v9.data.governance import HistoricalBar, require_dataset_ready
from gold_cio_v9.labels.outcomes import label_long, label_short


Direction = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class TradeCandidate:
    candidate_id: str
    signal_index: int
    direction: Direction
    entry: float
    stop: float
    target: float
    horizon_bars: int

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")
        if self.signal_index < 0 or self.horizon_bars <= 0:
            raise ValueError("signal_index must be >=0 and horizon_bars >0")
        if not all(isfinite(v) for v in (self.entry, self.stop, self.target)):
            raise ValueError("entry/stop/target must be finite")
        if self.direction == "LONG" and not (self.stop < self.entry < self.target):
            raise ValueError("invalid LONG geometry")
        if self.direction == "SHORT" and not (self.target < self.entry < self.stop):
            raise ValueError("invalid SHORT geometry")


@dataclass(frozen=True)
class TradeResult:
    candidate_id: str
    signal_index: int
    direction: Direction
    first_touch: str
    bars_to_first_touch: int | None
    mfe_r: float
    mae_r: float
    gross_realized_r: float
    gross_pnl_price: float
    net_pnl_price: float


@dataclass(frozen=True)
class BacktestResult:
    instrument: str
    data_snapshot_hash: str
    candidate_snapshot_hash: str
    result_hash: str
    trades: tuple[TradeResult, ...]


def _stable_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return sha256(encoded).hexdigest()


def hash_bars(bars: Sequence[HistoricalBar]) -> str:
    return _stable_hash([asdict(b) for b in bars])


def hash_candidates(candidates: Sequence[TradeCandidate]) -> str:
    return _stable_hash([asdict(c) for c in candidates])


def run_backtest(
    *,
    bars: Sequence[HistoricalBar],
    candidates: Sequence[TradeCandidate],
    instrument: str,
    costs: CostAssumptions,
) -> BacktestResult:
    """Run deterministic bar-based evidence replay.

    Candidates are assumed to have been generated causally upstream. The runner
    never creates or tunes signals. Ambiguous same-bar target/stop outcomes are
    preserved with NaN realized R and must be handled explicitly by validation.
    """
    materialized = list(bars)
    require_dataset_ready(materialized, instrument=instrument)
    if not candidates:
        raise ValueError("no candidates supplied")

    out: list[TradeResult] = []
    n = len(materialized)
    for c in candidates:
        if c.signal_index >= n - 1:
            raise ValueError(f"candidate {c.candidate_id} has no future bars")
        end = min(n, c.signal_index + 1 + c.horizon_bars)
        future = [(b.high, b.low, b.close) for b in materialized[c.signal_index + 1 : end]]
        if c.direction == "LONG":
            label = label_long(c.entry, c.stop, c.target, future)
            risk_price = c.entry - c.stop
            gross_price = label.realized_r * risk_price
        else:
            label = label_short(c.entry, c.stop, c.target, future)
            risk_price = c.stop - c.entry
            gross_price = label.realized_r * risk_price
        net_price = net_pnl_price(gross_price, costs) if isfinite(gross_price) else float("nan")
        out.append(
            TradeResult(
                candidate_id=c.candidate_id,
                signal_index=c.signal_index,
                direction=c.direction,
                first_touch=label.first_touch,
                bars_to_first_touch=label.bars_to_first_touch,
                mfe_r=label.mfe_r,
                mae_r=label.mae_r,
                gross_realized_r=label.realized_r,
                gross_pnl_price=gross_price,
                net_pnl_price=net_price,
            )
        )

    data_hash = hash_bars(materialized)
    candidate_hash = hash_candidates(candidates)
    result_payload = [asdict(t) for t in out]
    result_hash = _stable_hash(
        {
            "instrument": instrument,
            "data_snapshot_hash": data_hash,
            "candidate_snapshot_hash": candidate_hash,
            "costs": asdict(costs),
            "trades": result_payload,
        }
    )
    return BacktestResult(instrument, data_hash, candidate_hash, result_hash, tuple(out))
