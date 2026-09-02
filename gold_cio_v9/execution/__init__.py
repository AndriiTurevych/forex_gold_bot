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
from .durable_idempotency import DurableIdempotencyStore, Reservation, ReservationStatus
from .clock_health import ClockDecision, ClockLimits, ClockSample, evaluate_clock
from .feed_health import FeedDecision, FeedLimits, FeedSnapshot, evaluate_feed
from .watchdog import ExecutionWatchdog, KillReason, WatchdogStatus

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
    "DurableIdempotencyStore",
    "Reservation",
    "ReservationStatus",
    "ClockDecision",
    "ClockLimits",
    "ClockSample",
    "evaluate_clock",
    "FeedDecision",
    "FeedLimits",
    "FeedSnapshot",
    "evaluate_feed",
    "ExecutionWatchdog",
    "KillReason",
    "WatchdogStatus",
]
