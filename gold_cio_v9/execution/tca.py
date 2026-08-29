"""Transaction-cost attribution for shadow/live execution diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class TCAInput:
    side: str
    theoretical_entry: float
    decision_price: float
    submit_price: float
    fill_price: float
    exit_price: float
    fees_points: float

    def __post_init__(self) -> None:
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        vals = (
            self.theoretical_entry,
            self.decision_price,
            self.submit_price,
            self.fill_price,
            self.exit_price,
            self.fees_points,
        )
        if not all(isfinite(v) for v in vals):
            raise ValueError("all TCA values must be finite")
        if min(self.theoretical_entry, self.decision_price, self.submit_price, self.fill_price, self.exit_price) <= 0:
            raise ValueError("prices must be positive")
        if self.fees_points < 0:
            raise ValueError("fees_points cannot be negative")


@dataclass(frozen=True)
class TCAResult:
    gross_alpha_points: float
    decision_latency_cost_points: float
    submit_latency_cost_points: float
    fill_slippage_points: float
    fees_points: float
    realized_net_points: float
    execution_drag_points: float


def _signed_move(side: str, start: float, end: float) -> float:
    """PnL-oriented signed move from start to end."""
    return end - start if side == "BUY" else start - end


def _adverse_entry_move(side: str, start: float, end: float) -> float:
    """Positive when a later executable entry is worse than an earlier one."""
    return max(0.0, end - start) if side == "BUY" else max(0.0, start - end)


def analyze_tca(item: TCAInput) -> TCAResult:
    gross_alpha = _signed_move(item.side, item.theoretical_entry, item.exit_price)
    decision_cost = _adverse_entry_move(item.side, item.theoretical_entry, item.decision_price)
    submit_cost = _adverse_entry_move(item.side, item.decision_price, item.submit_price)
    fill_slippage = _adverse_entry_move(item.side, item.submit_price, item.fill_price)
    realized = _signed_move(item.side, item.fill_price, item.exit_price) - item.fees_points
    drag = gross_alpha - realized
    return TCAResult(
        gross_alpha_points=gross_alpha,
        decision_latency_cost_points=decision_cost,
        submit_latency_cost_points=submit_cost,
        fill_slippage_points=fill_slippage,
        fees_points=item.fees_points,
        realized_net_points=realized,
        execution_drag_points=drag,
    )
