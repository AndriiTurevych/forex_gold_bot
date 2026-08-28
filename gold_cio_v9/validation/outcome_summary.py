"""Deterministic OOS outcome aggregation for EXP-0001 evidence runs.

Ambiguous same-bar outcomes are excluded from realized metrics by policy and are
reported explicitly so the acceptance layer can fail closed on data resolution risk.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from gold_cio_v9.backtest.runner import BacktestResult
from gold_cio_v9.validation.metrics import (
    TradeMetrics,
    removal_top_trades_expectancy,
    top_fraction_pnl_share,
    trade_metrics,
)


@dataclass(frozen=True)
class OutcomeSummary:
    total_candidates: int
    resolved_trades: int
    ambiguous_trades: int
    ambiguity_rate: float
    metrics: TradeMetrics
    top_5pct_positive_pnl_share: float
    expectancy_after_top_5pct_removal: float


def summarize_oos(result: BacktestResult) -> OutcomeSummary:
    """Summarize one immutable OOS backtest result without imputing ambiguity."""
    trades = list(result.trades)
    if not trades:
        raise ValueError("backtest contains no trades")

    ambiguous = [t for t in trades if t.first_touch == "AMBIGUOUS"]
    resolved = [t for t in trades if t.first_touch != "AMBIGUOUS" and isfinite(t.net_pnl_price)]
    if not resolved:
        raise ValueError("no resolved OOS trades")

    pnls = [t.net_pnl_price for t in resolved]
    metrics = trade_metrics(pnls)
    concentration = top_fraction_pnl_share(pnls, 0.05)
    if len(pnls) == 1:
        removal_expectancy = float("nan")
    else:
        removal_expectancy = removal_top_trades_expectancy(pnls, 0.05)

    return OutcomeSummary(
        total_candidates=len(trades),
        resolved_trades=len(resolved),
        ambiguous_trades=len(ambiguous),
        ambiguity_rate=len(ambiguous) / len(trades),
        metrics=metrics,
        top_5pct_positive_pnl_share=concentration,
        expectancy_after_top_5pct_removal=removal_expectancy,
    )
