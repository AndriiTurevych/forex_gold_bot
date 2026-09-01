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
from .journal import JournalEvent, SQLiteExecutionJournal, replay
from .reconciliation import ReconciliationResult, ReconciliationSnapshot, reconcile
from .shadow_live import TwinComparison, TwinFill, compare_shadow_live
from .broker_contract import BrokerAck, BrokerAdapter, BrokerOrderRequest, OrderType, TimeInForce

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
    "JournalEvent",
    "SQLiteExecutionJournal",
    "replay",
    "ReconciliationSnapshot",
    "ReconciliationResult",
    "reconcile",
    "TwinFill",
    "TwinComparison",
    "compare_shadow_live",
    "BrokerOrderRequest",
    "BrokerAck",
    "BrokerAdapter",
    "OrderType",
    "TimeInForce",
]
