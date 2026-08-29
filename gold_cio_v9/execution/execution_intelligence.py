"""Deterministic execution-mode selector.

Chooses urgency/order style only after a trade is already approved. It does not
create alpha and cannot override risk or safety vetoes.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class ExecutionMode(str, Enum):
    MARKET = "MARKET"
    AGGRESSIVE_LIMIT = "AGGRESSIVE_LIMIT"
    PASSIVE_LIMIT = "PASSIVE_LIMIT"
    DO_NOT_ROUTE = "DO_NOT_ROUTE"


@dataclass(frozen=True)
class ExecutionState:
    spread_points: float
    volatility_ratio: float
    liquidity_score: float
    urgency_score: float
    expected_edge_points: float
    estimated_cost_points: float


@dataclass(frozen=True)
class ExecutionLimits:
    max_spread_points: float = 0.50
    min_liquidity_score: float = 0.25
    min_net_edge_points: float = 0.20


@dataclass(frozen=True)
class ExecutionDecision:
    mode: ExecutionMode
    reason: str


def choose_execution(state: ExecutionState, limits: ExecutionLimits = ExecutionLimits()) -> ExecutionDecision:
    vals = (
        state.spread_points,
        state.volatility_ratio,
        state.liquidity_score,
        state.urgency_score,
        state.expected_edge_points,
        state.estimated_cost_points,
    )
    if not all(isfinite(v) for v in vals):
        return ExecutionDecision(ExecutionMode.DO_NOT_ROUTE, "INVALID_EXECUTION_STATE")
    if state.spread_points < 0 or state.volatility_ratio <= 0 or state.estimated_cost_points < 0:
        return ExecutionDecision(ExecutionMode.DO_NOT_ROUTE, "INVALID_EXECUTION_STATE")
    if not (0.0 <= state.liquidity_score <= 1.0 and 0.0 <= state.urgency_score <= 1.0):
        return ExecutionDecision(ExecutionMode.DO_NOT_ROUTE, "INVALID_EXECUTION_STATE")
    if state.spread_points > limits.max_spread_points:
        return ExecutionDecision(ExecutionMode.DO_NOT_ROUTE, "SPREAD_TOO_WIDE")
    if state.liquidity_score < limits.min_liquidity_score:
        return ExecutionDecision(ExecutionMode.DO_NOT_ROUTE, "LIQUIDITY_TOO_THIN")
    net_edge = state.expected_edge_points - state.estimated_cost_points
    if net_edge < limits.min_net_edge_points:
        return ExecutionDecision(ExecutionMode.DO_NOT_ROUTE, "NET_EDGE_TOO_SMALL")
    if state.urgency_score >= 0.80 and state.liquidity_score >= 0.60:
        return ExecutionDecision(ExecutionMode.MARKET, "HIGH_URGENCY")
    if state.urgency_score >= 0.45 or state.volatility_ratio >= 1.25:
        return ExecutionDecision(ExecutionMode.AGGRESSIVE_LIMIT, "BALANCED_URGENCY")
    return ExecutionDecision(ExecutionMode.PASSIVE_LIMIT, "LOW_URGENCY")
