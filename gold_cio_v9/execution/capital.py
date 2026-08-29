"""Conservative capital allocation primitive for approved trades."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class CapitalState:
    base_risk_fraction: float
    edge_confidence: float
    regime_confidence: float
    liquidity_quality: float
    drawdown_fraction: float
    correlation_penalty: float
    margin_headroom_fraction: float


@dataclass(frozen=True)
class CapitalLimits:
    hard_max_risk_fraction: float = 0.0025
    max_drawdown_fraction: float = 0.025
    min_margin_headroom_fraction: float = 0.30


@dataclass(frozen=True)
class CapitalDecision:
    approved: bool
    risk_fraction: float
    reason: str


def allocate_capital(state: CapitalState, limits: CapitalLimits = CapitalLimits()) -> CapitalDecision:
    values = (
        state.base_risk_fraction,
        state.edge_confidence,
        state.regime_confidence,
        state.liquidity_quality,
        state.drawdown_fraction,
        state.correlation_penalty,
        state.margin_headroom_fraction,
    )
    if not all(isfinite(v) for v in values):
        return CapitalDecision(False, 0.0, "INVALID_CAPITAL_STATE")
    if state.base_risk_fraction <= 0 or state.drawdown_fraction < 0:
        return CapitalDecision(False, 0.0, "INVALID_CAPITAL_STATE")
    bounded = (
        state.edge_confidence,
        state.regime_confidence,
        state.liquidity_quality,
        state.correlation_penalty,
        state.margin_headroom_fraction,
    )
    if not all(0.0 <= v <= 1.0 for v in bounded):
        return CapitalDecision(False, 0.0, "INVALID_CAPITAL_STATE")
    if state.drawdown_fraction >= limits.max_drawdown_fraction:
        return CapitalDecision(False, 0.0, "DRAWDOWN_LOCK")
    if state.margin_headroom_fraction < limits.min_margin_headroom_fraction:
        return CapitalDecision(False, 0.0, "MARGIN_HEADROOM_VETO")
    risk = min(state.base_risk_fraction, limits.hard_max_risk_fraction)
    risk *= state.edge_confidence
    risk *= state.regime_confidence
    risk *= state.liquidity_quality
    risk *= 1.0 - state.correlation_penalty
    drawdown_scalar = max(0.0, 1.0 - state.drawdown_fraction / limits.max_drawdown_fraction)
    risk *= drawdown_scalar
    if risk <= 0:
        return CapitalDecision(False, 0.0, "ZERO_ALLOCATED_RISK")
    return CapitalDecision(True, risk, "APPROVED")
