"""Causal liquidity-aware GC front-contract selection for evidence datasets.

The selector uses only information that would have been known before the target
trading session: point-in-time contract metadata for ``as_of`` plus completed
prior-session volume. Current-session volume, open interest, future volume, price
outcomes, back-adjustment and hindsight roll dates are explicitly excluded.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite
from typing import Mapping, Sequence

from gold_cio_v9.data.contract_chain import ContractSpec, eligible_contracts


@dataclass(frozen=True)
class PriorSessionLiquidity:
    session_date: date
    volume_by_contract: Mapping[str, float]


def select_causal_liquid_front(
    specs: Sequence[ContractSpec],
    *,
    as_of: date,
    prior_liquidity: PriorSessionLiquidity,
    roll_buffer_days: int = 5,
) -> str:
    """Select the most liquid eligible outright GC contract using prior-session data.

    Rules:
    - liquidity must come from a session strictly before ``as_of``;
    - only contracts active on ``as_of`` and outside the locked expiry buffer compete;
    - every competing contract must have an explicit non-negative prior-session
      volume observation (zero is allowed; missing is not);
    - highest prior-session volume wins;
    - ties are resolved deterministically by nearest settlement then ticker;
    - no fallback to current-day data or a hindsight rule is permitted.
    """
    if roll_buffer_days < 0:
        raise ValueError("roll_buffer_days cannot be negative")
    if prior_liquidity.session_date >= as_of:
        raise ValueError("liquidity input must be from a completed prior session")

    candidates = [
        spec
        for spec in eligible_contracts(list(specs), as_of)
        if as_of <= spec.last_trade_date - timedelta(days=roll_buffer_days)
    ]
    if not candidates:
        raise ValueError("no eligible GC contracts outside expiry buffer")

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
