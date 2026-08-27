"""Deterministic validation metrics for evidence runs."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import mean
from typing import Iterable


@dataclass(frozen=True)
class TradeMetrics:
    count: int
    expectancy: float
    profit_factor: float
    win_rate: float
    pnl_total: float


def trade_metrics(net_pnls: Iterable[float]) -> TradeMetrics:
    values = [float(x) for x in net_pnls if isfinite(float(x))]
    if not values:
        raise ValueError("no finite PnL values")
    wins = [x for x in values if x > 0]
    losses = [x for x in values if x < 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    if gross_loss == 0:
        pf = float("inf") if gross_profit > 0 else 0.0
    else:
        pf = gross_profit / gross_loss
    return TradeMetrics(
        count=len(values),
        expectancy=mean(values),
        profit_factor=pf,
        win_rate=len(wins) / len(values),
        pnl_total=sum(values),
    )


def top_fraction_pnl_share(net_pnls: Iterable[float], fraction: float = 0.05) -> float:
    values = sorted((float(x) for x in net_pnls if isfinite(float(x))), reverse=True)
    if not values:
        raise ValueError("no finite PnL values")
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0,1]")
    total_positive = sum(x for x in values if x > 0)
    if total_positive <= 0:
        return 0.0
    n_top = max(1, int(round(len(values) * fraction)))
    return sum(max(0.0, x) for x in values[:n_top]) / total_positive


def removal_top_trades_expectancy(net_pnls: Iterable[float], fraction: float = 0.05) -> float:
    values = sorted((float(x) for x in net_pnls if isfinite(float(x))), reverse=True)
    if not values:
        raise ValueError("no finite PnL values")
    n_top = max(1, int(round(len(values) * fraction)))
    remaining = values[n_top:]
    if not remaining:
        raise ValueError("top-trade removal leaves no sample")
    return mean(remaining)
