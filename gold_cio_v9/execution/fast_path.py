"""Deterministic execution fast path.

Heavy context engines are expected to run continuously outside this function. The
fast path consumes already-computed context, a fresh trigger and a deterministic
risk veto. It performs no LLM/network calls and fails closed on stale inputs or
entry degradation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .latency import LatencyBudget


class FastPathDecision(str, Enum):
    TAKE = "TAKE"
    SKIP = "SKIP"
    STALE = "STALE"
    VETO = "VETO"


@dataclass(frozen=True)
class FastPathContext:
    computed_ns: int
    regime_allowed: bool
    location_allowed: bool
    macro_allowed: bool
    data_quality_ok: bool
    model_health_ok: bool


@dataclass(frozen=True)
class FastPathInput:
    signal_id: str
    trigger_ns: int
    decision_ns: int
    theoretical_entry: float
    current_price: float
    side: str
    alpha_qualified: bool
    meta_take: bool
    risk_veto: bool
    context: FastPathContext

    def __post_init__(self) -> None:
        if not self.signal_id.strip():
            raise ValueError("signal_id is required")
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if self.decision_ns < self.trigger_ns:
            raise ValueError("decision_ns precedes trigger_ns")
        if self.theoretical_entry <= 0 or self.current_price <= 0:
            raise ValueError("prices must be positive")


@dataclass(frozen=True)
class FastPathVerdict:
    decision: FastPathDecision
    reason: str
    trigger_age_ms: float
    context_age_ms: float
    decision_latency_ms: float
    adverse_entry_degradation_points: float


def _elapsed_ms(later_ns: int, earlier_ns: int) -> float:
    if later_ns < earlier_ns:
        raise ValueError("monotonic timestamp ordering violated")
    return (later_ns - earlier_ns) / 1_000_000.0


def _adverse_degradation(side: str, theoretical: float, current: float) -> float:
    # Positive means the executable price is worse than the theoretical entry.
    return max(0.0, current - theoretical) if side == "BUY" else max(0.0, theoretical - current)


def evaluate_fast_path(candidate: FastPathInput, budget: LatencyBudget) -> FastPathVerdict:
    """Return a fail-closed TAKE/SKIP/STALE/VETO decision without external calls."""
    trigger_age = _elapsed_ms(candidate.decision_ns, candidate.trigger_ns)
    context_age = _elapsed_ms(candidate.decision_ns, candidate.context.computed_ns)
    degradation = _adverse_degradation(
        candidate.side, candidate.theoretical_entry, candidate.current_price
    )

    def verdict(decision: FastPathDecision, reason: str) -> FastPathVerdict:
        return FastPathVerdict(
            decision=decision,
            reason=reason,
            trigger_age_ms=trigger_age,
            context_age_ms=context_age,
            decision_latency_ms=trigger_age,
            adverse_entry_degradation_points=degradation,
        )

    if trigger_age > budget.max_trigger_age_ms:
        return verdict(FastPathDecision.STALE, "TRIGGER_TOO_OLD")
    if context_age > budget.max_context_age_ms:
        return verdict(FastPathDecision.STALE, "CONTEXT_TOO_OLD")
    if trigger_age > budget.trigger_to_decision_ms:
        return verdict(FastPathDecision.STALE, "DECISION_LATENCY_BREACH")
    if not candidate.context.data_quality_ok:
        return verdict(FastPathDecision.VETO, "DATA_QUALITY_VETO")
    if not candidate.context.model_health_ok:
        return verdict(FastPathDecision.VETO, "MODEL_HEALTH_VETO")
    if candidate.risk_veto:
        return verdict(FastPathDecision.VETO, "RISK_VETO")
    if not candidate.context.regime_allowed:
        return verdict(FastPathDecision.SKIP, "REGIME_NOT_ALLOWED")
    if not candidate.context.location_allowed:
        return verdict(FastPathDecision.SKIP, "LOCATION_NOT_ALLOWED")
    if not candidate.context.macro_allowed:
        return verdict(FastPathDecision.SKIP, "MACRO_NOT_ALLOWED")
    if not candidate.alpha_qualified:
        return verdict(FastPathDecision.SKIP, "ALPHA_NOT_QUALIFIED")
    if not candidate.meta_take:
        return verdict(FastPathDecision.SKIP, "META_LABEL_SKIP")
    if degradation > budget.max_entry_degradation_points:
        return verdict(FastPathDecision.STALE, "ENTRY_DEGRADED")
    return verdict(FastPathDecision.TAKE, "FAST_PATH_APPROVED")
