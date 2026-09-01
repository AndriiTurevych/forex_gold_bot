"""Shadow/live twin comparison primitives."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class TwinFill:
    signal_id: str
    side: str
    price: float
    qty: int

    def __post_init__(self) -> None:
        if not self.signal_id.strip():
            raise ValueError("signal_id is required")
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if not isfinite(self.price) or self.price <= 0:
            raise ValueError("price must be finite and positive")
        if self.qty <= 0:
            raise ValueError("qty must be positive")


@dataclass(frozen=True)
class TwinComparison:
    matched: bool
    reason: str
    price_divergence_points: float
    qty_divergence: int


def compare_shadow_live(shadow: TwinFill, live: TwinFill, *, max_price_divergence_points: float) -> TwinComparison:
    if max_price_divergence_points < 0 or not isfinite(max_price_divergence_points):
        raise ValueError("max_price_divergence_points must be finite and non-negative")
    if shadow.signal_id != live.signal_id:
        return TwinComparison(False, "SIGNAL_ID_MISMATCH", float("inf"), abs(shadow.qty - live.qty))
    if shadow.side != live.side:
        return TwinComparison(False, "SIDE_MISMATCH", float("inf"), abs(shadow.qty - live.qty))
    qty_div = abs(shadow.qty - live.qty)
    price_div = abs(shadow.price - live.price)
    if qty_div:
        return TwinComparison(False, "QUANTITY_MISMATCH", price_div, qty_div)
    if price_div > max_price_divergence_points:
        return TwinComparison(False, "PRICE_DIVERGENCE", price_div, qty_div)
    return TwinComparison(True, "MATCHED", price_div, qty_div)
