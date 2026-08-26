"""Deterministic position sizing for Gold CIO v9.1.

Sizing is separate from alpha and risk approval. No AI/model may override hard caps.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SizingInputs:
    equity: float
    risk_fraction: float
    entry: float
    stop: float
    point_value: float
    volatility_scale: float = 1.0
    correlation_scale: float = 1.0
    drawdown_scale: float = 1.0
    kelly_fraction: float = 0.0
    kelly_cap: float = 0.25
    max_risk_fraction: float = 0.0025


@dataclass(frozen=True)
class SizingDecision:
    units: float
    cash_risk: float
    effective_risk_fraction: float
    reason: str


def size_position(x: SizingInputs) -> SizingDecision:
    if x.equity <= 0 or x.point_value <= 0:
        raise ValueError("equity and point_value must be positive")
    stop_distance = abs(x.entry - x.stop)
    if stop_distance <= 0:
        raise ValueError("stop distance must be positive")
    if not (0 < x.volatility_scale <= 1 and 0 < x.correlation_scale <= 1 and 0 < x.drawdown_scale <= 1):
        raise ValueError("scales must be in (0, 1]")

    requested = min(x.risk_fraction, x.max_risk_fraction)

    # Fractional Kelly may only reduce sizing; it never increases above the hard risk cap.
    if x.kelly_fraction > 0:
        requested = min(requested, x.kelly_fraction * x.kelly_cap)

    effective = requested * x.volatility_scale * x.correlation_scale * x.drawdown_scale
    cash_risk = x.equity * effective
    units = cash_risk / (stop_distance * x.point_value)

    return SizingDecision(
        units=max(units, 0.0),
        cash_risk=cash_risk,
        effective_risk_fraction=effective,
        reason="DETERMINISTIC_SIZING",
    )
