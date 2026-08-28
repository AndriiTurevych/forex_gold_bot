"""Deterministic point-in-time front-contract calendar for GC evidence datasets.

Consumes a complete PIT contract snapshot per requested date and applies the locked
expiry-buffer policy independently for each date. No volume/open-interest ranking,
back adjustment, interpolation, or hindsight switching is performed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from gold_cio_v9.data.massive_contracts import select_massive_gc_front


@dataclass(frozen=True)
class FrontContractDay:
    as_of: date
    contract: str


@dataclass(frozen=True)
class FrontContractCalendar:
    days: tuple[FrontContractDay, ...]
    contract_order: tuple[str, ...]


def build_front_contract_calendar(
    snapshots: Mapping[date, Sequence[Mapping[str, object]]],
    *,
    dates: Sequence[date],
    roll_buffer_days: int = 5,
) -> FrontContractCalendar:
    """Build a fully auditable PIT daily front-contract assignment.

    `dates` is caller-supplied and therefore explicit/precommitted. Every requested
    date must have a PIT snapshot and must resolve to one deterministic outright GC
    contract; otherwise the calendar fails closed.
    """
    if roll_buffer_days < 0:
        raise ValueError("roll_buffer_days cannot be negative")
    if not dates:
        raise ValueError("dates are required")
    if len(set(dates)) != len(dates):
        raise ValueError("dates contain duplicates")
    if any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValueError("dates must be strictly increasing")

    out: list[FrontContractDay] = []
    order: list[str] = []
    seen_contracts: set[str] = set()

    for as_of in dates:
        rows = snapshots.get(as_of)
        if rows is None:
            raise ValueError(f"missing PIT contract snapshot for {as_of.isoformat()}")
        contract = select_massive_gc_front(
            rows,
            as_of=as_of,
            roll_buffer_days=roll_buffer_days,
        )
        if contract is None:
            raise ValueError(f"no eligible front GC contract for {as_of.isoformat()}")
        out.append(FrontContractDay(as_of=as_of, contract=contract))
        if contract not in seen_contracts:
            seen_contracts.add(contract)
            order.append(contract)

    # A deterministic front chain must never return to an older contract after a
    # later contract was selected. Re-entry would indicate inconsistent snapshots
    # or a non-monotonic metadata history and must block evidence assembly.
    first_pos = {contract: i for i, contract in enumerate(order)}
    last_rank = -1
    for day in out:
        rank = first_pos[day.contract]
        if rank < last_rank:
            raise ValueError("front-contract calendar re-enters an older contract")
        last_rank = rank

    return FrontContractCalendar(days=tuple(out), contract_order=tuple(order))
