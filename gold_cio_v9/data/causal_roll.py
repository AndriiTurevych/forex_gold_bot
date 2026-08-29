"""Causal liquidity-aware GC front-contract selection for evidence datasets.

Uses only PIT contract metadata plus completed prior-session volume. The locked V2
candidate universe excludes far-dated tail listings whose settlement is more than
365 calendar days after the decision date.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite
from typing import Mapping, Sequence

from gold_cio_v9.data.contract_chain import ContractSpec, eligible_contracts

MAX_SETTLEMENT_DAYS_FORWARD = 365


@dataclass(frozen=True)
class PriorSessionLiquidity:
    session_date: date
    volume_by_contract: Mapping[str, float]


def causal_front_candidates(
    specs: Sequence[ContractSpec],
    *,
    as_of: date,
    roll_buffer_days: int = 5,
    max_settlement_days_forward: int = MAX_SETTLEMENT_DAYS_FORWARD,
) -> tuple[ContractSpec, ...]:
    if roll_buffer_days < 0:
        raise ValueError("roll_buffer_days cannot be negative")
    if max_settlement_days_forward <= 0:
        raise ValueError("max_settlement_days_forward must be positive")
    max_settlement = as_of + timedelta(days=max_settlement_days_forward)
    candidates = [
        spec
        for spec in eligible_contracts(list(specs), as_of)
        if as_of <= spec.last_trade_date - timedelta(days=roll_buffer_days)
        and spec.settlement_date <= max_settlement
    ]
    if not candidates:
        raise ValueError("no eligible GC contracts in locked front universe")
    return tuple(sorted(candidates, key=lambda s: (s.settlement_date, s.ticker)))


def select_causal_liquid_front(
    specs: Sequence[ContractSpec],
    *,
    as_of: date,
    prior_liquidity: PriorSessionLiquidity,
    roll_buffer_days: int = 5,
    max_settlement_days_forward: int = MAX_SETTLEMENT_DAYS_FORWARD,
) -> str:
    """Select highest prior-session volume inside the locked causal front universe."""
    if prior_liquidity.session_date >= as_of:
        raise ValueError("liquidity input must be from a completed prior session")
    candidates = causal_front_candidates(
        specs,
        as_of=as_of,
        roll_buffer_days=roll_buffer_days,
        max_settlement_days_forward=max_settlement_days_forward,
    )
    ranked: list[tuple[float, date, str]] = []
    for spec in candidates:
        if spec.ticker not in prior_liquidity.volume_by_contract:
            raise ValueError(f"missing prior-session volume for {spec.ticker}")
        raw = prior_liquidity.volume_by_contract[spec.ticker]
        try:
            volume = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid prior-session volume for {spec.ticker}") from exc
        if not isfinite(volume) or volume < 0:
            raise ValueError(f"invalid prior-session volume for {spec.ticker}")
        ranked.append((-volume, spec.settlement_date, spec.ticker))
    ranked.sort()
    return ranked[0][2]
