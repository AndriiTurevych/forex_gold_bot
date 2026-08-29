"""Deterministic, fail-closed order lifecycle primitives."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILED = "RECONCILED"


_ALLOWED: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {OrderStatus.SUBMITTED, OrderStatus.REJECTED},
    OrderStatus.SUBMITTED: {
        OrderStatus.ACKNOWLEDGED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.REJECTED,
        OrderStatus.UNKNOWN,
    },
    OrderStatus.ACKNOWLEDGED: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.CANCELED,
        OrderStatus.REJECTED,
        OrderStatus.UNKNOWN,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.CANCELED,
        OrderStatus.UNKNOWN,
    },
    OrderStatus.CANCEL_PENDING: {
        OrderStatus.CANCELED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.UNKNOWN,
    },
    OrderStatus.FILLED: {OrderStatus.RECONCILED},
    OrderStatus.CANCELED: {OrderStatus.RECONCILED},
    OrderStatus.REJECTED: {OrderStatus.RECONCILED},
    OrderStatus.UNKNOWN: {
        OrderStatus.ACKNOWLEDGED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.REJECTED,
        OrderStatus.RECONCILED,
    },
    OrderStatus.RECONCILED: set(),
}


@dataclass(frozen=True)
class OrderState:
    client_order_id: str
    status: OrderStatus = OrderStatus.CREATED
    requested_qty: int = 0
    filled_qty: int = 0

    def __post_init__(self) -> None:
        if not self.client_order_id.strip():
            raise ValueError("client_order_id is required")
        if self.requested_qty <= 0:
            raise ValueError("requested_qty must be positive")
        if self.filled_qty < 0 or self.filled_qty > self.requested_qty:
            raise ValueError("invalid filled_qty")


def transition(order: OrderState, new_status: OrderStatus, *, filled_qty: int | None = None) -> OrderState:
    if new_status not in _ALLOWED[order.status]:
        raise ValueError(f"illegal order transition: {order.status.value}->{new_status.value}")
    qty = order.filled_qty if filled_qty is None else filled_qty
    if qty < order.filled_qty:
        raise ValueError("filled_qty cannot decrease")
    if qty > order.requested_qty:
        raise ValueError("filled_qty exceeds requested_qty")
    if new_status is OrderStatus.FILLED and qty != order.requested_qty:
        raise ValueError("FILLED requires full requested quantity")
    if new_status is OrderStatus.PARTIALLY_FILLED and not (0 < qty < order.requested_qty):
        raise ValueError("PARTIALLY_FILLED requires 0 < filled_qty < requested_qty")
    return replace(order, status=new_status, filled_qty=qty)
