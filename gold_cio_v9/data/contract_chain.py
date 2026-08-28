"""Deterministic raw-contract chain policy for EXP-0001 evidence datasets.

This module never back-adjusts prices and never blends two contracts into one bar.
Contract selection is explicit, auditable, and based only on supplied point-in-time
contract metadata. Roll buffers are excluded rather than synthesized.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class ContractSpec:
    ticker: str
    first_trade_date: date
    last_trade_date: date
    settlement_date: date

    def __post_init__(self) -> None:
        if not self.ticker.startswith("GC") or "-" in self.ticker:
            raise ValueError("EXP-0001 chain accepts outright GC contracts only")
        if self.last_trade_date < self.first_trade_date:
            raise ValueError("last_trade_date precedes first_trade_date")


def eligible_contracts(specs: list[ContractSpec], as_of: date) -> list[ContractSpec]:
    """Return contracts known to be tradeable on as_of, nearest maturity first."""
    active = [s for s in specs if s.first_trade_date <= as_of <= s.last_trade_date]
    return sorted(active, key=lambda s: (s.settlement_date, s.ticker))


def select_front_contract(specs: list[ContractSpec], as_of: date, *, roll_buffer_days: int = 5) -> str | None:
    """Select nearest active outright contract outside a precommitted expiry buffer.

    The rule is intentionally mechanical. If the nearest contract is inside the
    buffer it is skipped in favour of the next eligible maturity. If none exists,
    fail closed with None. No volume/open-interest hindsight is used.
    """
    if roll_buffer_days < 0:
        raise ValueError("roll_buffer_days cannot be negative")
    for spec in eligible_contracts(specs, as_of):
        if as_of <= spec.last_trade_date - timedelta(days=roll_buffer_days):
            return spec.ticker
    return None


def is_roll_buffer(spec: ContractSpec, as_of: date, *, roll_buffer_days: int = 5) -> bool:
    if roll_buffer_days < 0:
        raise ValueError("roll_buffer_days cannot be negative")
    if not (spec.first_trade_date <= as_of <= spec.last_trade_date):
        return False
    return as_of > spec.last_trade_date - timedelta(days=roll_buffer_days)
