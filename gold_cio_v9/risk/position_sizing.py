"""Deterministic position sizing for Gold CIO v9.1.

Sizing is separate from alpha and risk approval. No AI/model may override hard caps.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


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


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")


def size_position(x: SizingInputs) -> SizingDecision:
    for name, value in (
        ("equity", x.equity),
        ("risk_fraction", x.risk_fraction),
        ("entry", x.entry),
        ("stop", x.stop),
        ("point_value", x.point_value),
        ("volatility_scale", x.volatility_scale),
        ("correlation_scale", x.correlation_scale),
        ("drawdown_scale", x.drawdown_scale),
        ("kelly_fraction", x.kelly_fraction),
        ("kelly_cap", x.kelly_cap),
        ("max_risk_fraction", x.max_risk_fraction),
    ):
        _require_finite(name, value)

    if x.equity <= 0 or x.point_value <= 0:
        raise ValueError("equity and point_value must be positive")
    if x.risk_fraction < 0 or x.max_risk_fraction <= 0:
        raise ValueError("risk fractions must be non-negative and max_risk_fraction positive")
    if x.kelly_fraction < 0 or not (0 < x.kelly_cap <= 1):
        raise ValueError("kelly_fraction must be non-negative and kelly_cap in (0, 1]")

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
        units=units,
        cash_risk=cash_risk,
        effective_risk_fraction=effective,
        reason="DETERMINISTIC_SIZING",
    )
