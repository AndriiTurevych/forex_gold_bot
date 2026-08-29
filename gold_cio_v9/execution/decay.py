"""Deterministic strategy-decay controls for shadow/live operations.

This module does not alter alpha generation. It converts rolling forward-performance
health into an allowed capital mode.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class RiskMode(str, Enum):
    FULL = "FULL"
    HALF = "HALF"
    SHADOW_ONLY = "SHADOW_ONLY"
    OFF = "OFF"


@dataclass(frozen=True)
class DecayLimits:
    min_expectancy_r_full: float = 0.10
    min_expectancy_r_half: float = 0.00
    min_profit_factor_full: float = 1.20
    min_profit_factor_half: float = 1.00
    max_live_shadow_divergence_r: float = 0.20
    min_resolved_trades: int = 20

    def __post_init__(self) -> None:
        if self.min_resolved_trades <= 0:
            raise ValueError("min_resolved_trades must be positive")
        if self.min_profit_factor_full < self.min_profit_factor_half:
            raise ValueError("full PF threshold cannot be below half threshold")
        if self.min_expectancy_r_full < self.min_expectancy_r_half:
            raise ValueError("full expectancy threshold cannot be below half threshold")
        if self.max_live_shadow_divergence_r < 0:
            raise ValueError("divergence limit cannot be negative")


@dataclass(frozen=True)
class DecayState:
    resolved_trades: int
    rolling_expectancy_r: float
    rolling_profit_factor: float
    live_shadow_divergence_r: float
    model_health_ok: bool
    execution_health_ok: bool


@dataclass(frozen=True)
class DecayDecision:
    mode: RiskMode
    risk_multiplier: float
    reason: str


def evaluate_decay(state: DecayState, limits: DecayLimits = DecayLimits()) -> DecayDecision:
    numeric = (
        state.rolling_expectancy_r,
        state.rolling_profit_factor,
        state.live_shadow_divergence_r,
    )
    if state.resolved_trades < 0 or not all(isfinite(v) for v in numeric):
        return DecayDecision(RiskMode.OFF, 0.0, "INVALID_DECAY_STATE")
    if not state.model_health_ok:
        return DecayDecision(RiskMode.OFF, 0.0, "MODEL_HEALTH_FAILURE")
    if not state.execution_health_ok:
        return DecayDecision(RiskMode.SHADOW_ONLY, 0.0, "EXECUTION_HEALTH_FAILURE")
    if state.live_shadow_divergence_r > limits.max_live_shadow_divergence_r:
        return DecayDecision(RiskMode.SHADOW_ONLY, 0.0, "LIVE_SHADOW_DIVERGENCE")
    if state.resolved_trades < limits.min_resolved_trades:
        return DecayDecision(RiskMode.HALF, 0.5, "INSUFFICIENT_FORWARD_SAMPLE")
    if (
        state.rolling_expectancy_r >= limits.min_expectancy_r_full
        and state.rolling_profit_factor >= limits.min_profit_factor_full
    ):
        return DecayDecision(RiskMode.FULL, 1.0, "HEALTHY")
    if (
        state.rolling_expectancy_r >= limits.min_expectancy_r_half
        and state.rolling_profit_factor >= limits.min_profit_factor_half
    ):
        return DecayDecision(RiskMode.HALF, 0.5, "DEGRADED")
    if state.rolling_expectancy_r < 0 or state.rolling_profit_factor < 1.0:
        return DecayDecision(RiskMode.OFF, 0.0, "EDGE_DECAY")
    return DecayDecision(RiskMode.SHADOW_ONLY, 0.0, "UNCERTAIN_EDGE")
