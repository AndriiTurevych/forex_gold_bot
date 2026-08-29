"""Latency budgets and telemetry for the Gold CIO deterministic fast path.

The critical path must be measurable and fail closed. All timestamps are monotonic
nanoseconds supplied by the caller; wall-clock time is deliberately excluded from
latency arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def _ns_to_ms(value_ns: int) -> float:
    if value_ns < 0:
        raise ValueError("duration cannot be negative")
    return value_ns / 1_000_000.0


@dataclass(frozen=True)
class LatencyBudget:
    """Hard latency and freshness limits for one execution decision."""

    trigger_to_decision_ms: float = 50.0
    decision_to_order_ms: float = 25.0
    total_signal_to_order_ms: float = 100.0
    max_trigger_age_ms: float = 250.0
    max_context_age_ms: float = 1_000.0
    max_entry_degradation_points: float = 0.30

    def __post_init__(self) -> None:
        values = (
            self.trigger_to_decision_ms,
            self.decision_to_order_ms,
            self.total_signal_to_order_ms,
            self.max_trigger_age_ms,
            self.max_context_age_ms,
            self.max_entry_degradation_points,
        )
        if any(v <= 0 for v in values):
            raise ValueError("all latency budget values must be positive")
        if self.total_signal_to_order_ms < self.trigger_to_decision_ms + self.decision_to_order_ms:
            raise ValueError("total_signal_to_order_ms cannot be smaller than stage budgets")


@dataclass(frozen=True)
class StageTiming:
    name: str
    started_ns: int
    completed_ns: int

    @property
    def elapsed_ms(self) -> float:
        if self.completed_ns < self.started_ns:
            raise ValueError("completed_ns precedes started_ns")
        return _ns_to_ms(self.completed_ns - self.started_ns)


@dataclass
class LatencyTrace:
    """Small append-only trace used for shadow/live latency diagnostics."""

    signal_id: str
    signal_created_ns: int
    stages: list[StageTiming] = field(default_factory=list)
    order_sent_ns: int | None = None

    def add_stage(self, name: str, started_ns: int, completed_ns: int) -> None:
        if not name.strip():
            raise ValueError("stage name is required")
        if completed_ns < started_ns:
            raise ValueError("completed_ns precedes started_ns")
        if self.stages and started_ns < self.stages[-1].started_ns:
            raise ValueError("stages must be appended in monotonic order")
        self.stages.append(StageTiming(name=name, started_ns=started_ns, completed_ns=completed_ns))

    def mark_order_sent(self, order_sent_ns: int) -> None:
        if order_sent_ns < self.signal_created_ns:
            raise ValueError("order_sent_ns precedes signal creation")
        self.order_sent_ns = order_sent_ns

    @property
    def signal_to_order_ms(self) -> float | None:
        if self.order_sent_ns is None:
            return None
        return _ns_to_ms(self.order_sent_ns - self.signal_created_ns)

    def stage_ms(self, name: str) -> float | None:
        matches = [stage.elapsed_ms for stage in self.stages if stage.name == name]
        if not matches:
            return None
        return sum(matches)

    def within_budget(self, budget: LatencyBudget) -> bool:
        total = self.signal_to_order_ms
        if total is not None and total > budget.total_signal_to_order_ms:
            return False
        decision = self.stage_ms("decision")
        if decision is not None and decision > budget.trigger_to_decision_ms:
            return False
        order = self.stage_ms("order_submit")
        if order is not None and order > budget.decision_to_order_ms:
            return False
        return True
