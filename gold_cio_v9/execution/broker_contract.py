"""Broker-neutral execution contract for paper/shadow/live adapters."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class TimeInForce(str, Enum):
    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


@dataclass(frozen=True)
class BrokerOrderRequest:
    client_order_id: str
    instrument: str
    side: str
    quantity: int
    order_type: OrderType
    tif: TimeInForce
    limit_price: float | None = None
    stop_price: float | None = None

    def __post_init__(self) -> None:
        if not self.client_order_id.strip() or not self.instrument.strip():
            raise ValueError("client_order_id and instrument are required")
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT} and (self.limit_price is None or self.limit_price <= 0):
            raise ValueError("limit price required")
        if self.order_type in {OrderType.STOP, OrderType.STOP_LIMIT} and (self.stop_price is None or self.stop_price <= 0):
            raise ValueError("stop price required")


@dataclass(frozen=True)
class BrokerAck:
    client_order_id: str
    broker_order_id: str
    accepted: bool
    reason: str = ""


class BrokerAdapter(Protocol):
    def submit(self, order: BrokerOrderRequest) -> BrokerAck: ...
    def cancel(self, broker_order_id: str) -> BrokerAck: ...
    def open_orders(self) -> tuple[BrokerAck, ...]: ...
    def position(self, instrument: str) -> int: ...
