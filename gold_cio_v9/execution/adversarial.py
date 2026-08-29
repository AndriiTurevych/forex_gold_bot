"""Adversarial pre-trade veto: attempt to falsify a trade before execution."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class AdversarialState:
    exhaustion_score: float
    trap_score: float
    regime_instability_score: float
    liquidity_vacuum_score: float
    rr_after_costs: float
    macro_risk: bool
    location_valid: bool


@dataclass(frozen=True)
class AdversarialLimits:
    max_exhaustion_score: float = 0.80
    max_trap_score: float = 0.75
    max_regime_instability_score: float = 0.70
    max_liquidity_vacuum_score: float = 0.75
    min_rr_after_costs: float = 1.50


@dataclass(frozen=True)
class AdversarialDecision:
    approved: bool
    reason: str


def evaluate_adversarial(state: AdversarialState, limits: AdversarialLimits = AdversarialLimits()) -> AdversarialDecision:
    scores = (
        state.exhaustion_score,
        state.trap_score,
        state.regime_instability_score,
        state.liquidity_vacuum_score,
    )
    if not all(isfinite(v) and 0.0 <= v <= 1.0 for v in scores):
        return AdversarialDecision(False, "INVALID_ADVERSARIAL_SCORE")
    if not isfinite(state.rr_after_costs) or state.rr_after_costs <= 0:
        return AdversarialDecision(False, "INVALID_RR")
    if state.macro_risk:
        return AdversarialDecision(False, "MACRO_RISK_VETO")
    if not state.location_valid:
        return AdversarialDecision(False, "LOCATION_VETO")
    if state.exhaustion_score > limits.max_exhaustion_score:
        return AdversarialDecision(False, "EXHAUSTION_VETO")
    if state.trap_score > limits.max_trap_score:
        return AdversarialDecision(False, "TRAP_VETO")
    if state.regime_instability_score > limits.max_regime_instability_score:
        return AdversarialDecision(False, "REGIME_INSTABILITY_VETO")
    if state.liquidity_vacuum_score > limits.max_liquidity_vacuum_score:
        return AdversarialDecision(False, "LIQUIDITY_VACUUM_VETO")
    if state.rr_after_costs < limits.min_rr_after_costs:
        return AdversarialDecision(False, "RR_AFTER_COSTS_VETO")
    return AdversarialDecision(True, "APPROVED")
