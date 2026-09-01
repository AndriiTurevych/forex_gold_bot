"""Fail-closed reconciliation between local and broker truth."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class ReconciliationSnapshot:
    local_position: int
    broker_position: int
    local_open_orders: frozenset[str]
    broker_open_orders: frozenset[str]
    local_cash: float
    broker_cash: float
    cash_tolerance: float = 1.0

    def __post_init__(self) -> None:
        if self.cash_tolerance < 0 or not isfinite(self.cash_tolerance):
            raise ValueError("cash_tolerance must be finite and non-negative")
        if not all(isfinite(v) for v in (self.local_cash, self.broker_cash)):
            raise ValueError("cash values must be finite")


@dataclass(frozen=True)
class ReconciliationResult:
    reconciled: bool
    reason: str
    position_delta: int
    missing_local_orders: frozenset[str]
    missing_broker_orders: frozenset[str]
    cash_delta: float


def reconcile(snapshot: ReconciliationSnapshot) -> ReconciliationResult:
    position_delta = snapshot.broker_position - snapshot.local_position
    missing_local = snapshot.broker_open_orders - snapshot.local_open_orders
    missing_broker = snapshot.local_open_orders - snapshot.broker_open_orders
    cash_delta = snapshot.broker_cash - snapshot.local_cash

    if position_delta != 0:
        reason = "POSITION_MISMATCH"
    elif missing_local or missing_broker:
        reason = "OPEN_ORDER_MISMATCH"
    elif abs(cash_delta) > snapshot.cash_tolerance:
        reason = "CASH_MISMATCH"
    else:
        reason = "RECONCILED"

    return ReconciliationResult(
        reconciled=reason == "RECONCILED",
        reason=reason,
        position_delta=position_delta,
        missing_local_orders=frozenset(missing_local),
        missing_broker_orders=frozenset(missing_broker),
        cash_delta=cash_delta,
    )
