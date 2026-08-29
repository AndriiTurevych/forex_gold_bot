"""Daily causal liquidity-aware front-contract calendar for GC evidence data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from gold_cio_v9.data.causal_roll import PriorSessionLiquidity, select_causal_liquid_front
from gold_cio_v9.data.massive_contracts import parse_massive_gc_contracts


@dataclass(frozen=True)
class LiquidFrontDay:
    as_of: date
    liquidity_session_date: date
    contract: str


@dataclass(frozen=True)
class LiquidFrontCalendar:
    days: tuple[LiquidFrontDay, ...]
    contract_order: tuple[str, ...]


def build_liquid_front_calendar(
    snapshots: Mapping[date, Sequence[Mapping[str, object]]],
    prior_liquidity_by_date: Mapping[date, PriorSessionLiquidity],
    *,
    dates: Sequence[date],
    roll_buffer_days: int = 5,
) -> LiquidFrontCalendar:
    """Build a PIT daily chain using only completed prior-session liquidity.

    The caller supplies both the PIT metadata snapshot and the prior-session volume
    snapshot for every requested date. Missing evidence fails closed. Contract
    re-entry is prohibited so the resulting chain is monotonic and auditable.
    """
    if not dates:
        raise ValueError("dates are required")
    if len(set(dates)) != len(dates):
        raise ValueError("dates contain duplicates")
    if any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValueError("dates must be strictly increasing")

    out: list[LiquidFrontDay] = []
    order: list[str] = []
    seen: set[str] = set()

    for as_of in dates:
        rows = snapshots.get(as_of)
        if rows is None:
            raise ValueError(f"missing PIT contract snapshot for {as_of.isoformat()}")
        liquidity = prior_liquidity_by_date.get(as_of)
        if liquidity is None:
            raise ValueError(f"missing prior-session liquidity for {as_of.isoformat()}")
        specs = parse_massive_gc_contracts(rows, as_of=as_of)
        contract = select_causal_liquid_front(
            specs,
            as_of=as_of,
            prior_liquidity=liquidity,
            roll_buffer_days=roll_buffer_days,
        )
        out.append(LiquidFrontDay(as_of, liquidity.session_date, contract))
        if contract not in seen:
            seen.add(contract)
            order.append(contract)

    rank = {contract: i for i, contract in enumerate(order)}
    last_rank = -1
    for day in out:
        current_rank = rank[day.contract]
        if current_rank < last_rank:
            raise ValueError("liquidity-aware calendar re-enters an older contract")
        last_rank = current_rank

    return LiquidFrontCalendar(tuple(out), tuple(order))
