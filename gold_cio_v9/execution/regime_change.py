"""Simple deterministic regime-transition risk detector for execution de-risking."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class RegimeChangeState:
    volatility_ratio: float
    trend_strength_change: float
    spread_ratio: float
    directional_flip_count: int


@dataclass(frozen=True)
class RegimeChangeLimits:
    max_volatility_ratio: float = 1.50
    max_abs_trend_strength_change: float = 0.40
    max_spread_ratio: float = 2.00
    max_directional_flip_count: int = 3


@dataclass(frozen=True)
class RegimeChangeDecision:
    stable: bool
    risk_multiplier: float
    reason: str


def evaluate_regime_change(state: RegimeChangeState, limits: RegimeChangeLimits = RegimeChangeLimits()) -> RegimeChangeDecision:
    vals = (state.volatility_ratio, state.trend_strength_change, state.spread_ratio)
    if not all(isfinite(v) for v in vals) or state.volatility_ratio <= 0 or state.spread_ratio <= 0 or state.directional_flip_count < 0:
        return RegimeChangeDecision(False, 0.0, "INVALID_REGIME_STATE")
    severe = (
        state.volatility_ratio >= limits.max_volatility_ratio * 1.5
        or state.spread_ratio >= limits.max_spread_ratio * 1.5
        or state.directional_flip_count >= limits.max_directional_flip_count * 2
    )
    if severe:
        return RegimeChangeDecision(False, 0.0, "SEVERE_REGIME_TRANSITION")
    unstable = (
        state.volatility_ratio > limits.max_volatility_ratio
        or abs(state.trend_strength_change) > limits.max_abs_trend_strength_change
        or state.spread_ratio > limits.max_spread_ratio
        or state.directional_flip_count > limits.max_directional_flip_count
    )
    if unstable:
        return RegimeChangeDecision(False, 0.5, "REGIME_TRANSITION_RISK")
    return RegimeChangeDecision(True, 1.0, "STABLE")
