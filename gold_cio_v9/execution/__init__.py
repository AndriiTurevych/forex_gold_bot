"""Deterministic low-latency execution primitives for Gold CIO v9.1."""

from .latency import LatencyBudget, LatencyTrace, StageTiming
from .latency_stats import LatencyDistribution, summarize_latency
from .fast_path import FastPathContext, FastPathDecision, FastPathInput, FastPathVerdict, evaluate_fast_path
from .operational_safety import (
    IdempotencyRegistry,
    OperationalDecision,
    OperationalLimits,
    OperationalState,
    deterministic_order_key,
    evaluate_operational_safety,
)
from .order_state import OrderState, OrderStatus, transition

__all__ = [
    "LatencyBudget",
    "LatencyTrace",
    "StageTiming",
    "LatencyDistribution",
    "summarize_latency",
    "FastPathContext",
    "FastPathDecision",
    "FastPathInput",
    "FastPathVerdict",
    "evaluate_fast_path",
    "OperationalLimits",
    "OperationalState",
    "OperationalDecision",
    "evaluate_operational_safety",
    "deterministic_order_key",
    "IdempotencyRegistry",
    "OrderState",
    "OrderStatus",
    "transition",
]
