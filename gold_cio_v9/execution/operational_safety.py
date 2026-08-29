"""Operational safety controls independent from alpha and model logic."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite


@dataclass(frozen=True)
class OperationalLimits:
    max_clock_drift_ms: float = 100.0
    max_reject_rate: float = 0.05
    max_slippage_points: float = 0.50
    max_position_mismatch_contracts: int = 0

    def __post_init__(self) -> None:
        if self.max_clock_drift_ms <= 0 or self.max_slippage_points <= 0:
            raise ValueError("positive operational limits required")
        if not 0 <= self.max_reject_rate <= 1:
            raise ValueError("max_reject_rate must be in [0,1]")
        if self.max_position_mismatch_contracts < 0:
            raise ValueError("max_position_mismatch_contracts cannot be negative")


@dataclass(frozen=True)
class OperationalState:
    kill_switch_active: bool
    broker_connected: bool
    feed_connected: bool
    clock_drift_ms: float
    position_mismatch_contracts: int
    unknown_order_state: bool
    duplicate_order_detected: bool
    recent_reject_rate: float
    observed_slippage_points: float


@dataclass(frozen=True)
class OperationalDecision:
    approved: bool
    reason: str


def evaluate_operational_safety(state: OperationalState, limits: OperationalLimits = OperationalLimits()) -> OperationalDecision:
    numeric = (state.clock_drift_ms, state.recent_reject_rate, state.observed_slippage_points)
    if not all(isfinite(v) and v >= 0 for v in numeric):
        return OperationalDecision(False, "INVALID_OPERATIONAL_METRIC")
    if state.position_mismatch_contracts < 0:
        return OperationalDecision(False, "INVALID_POSITION_MISMATCH")
    if state.kill_switch_active:
        return OperationalDecision(False, "KILL_SWITCH_ACTIVE")
    if not state.broker_connected:
        return OperationalDecision(False, "BROKER_DISCONNECTED")
    if not state.feed_connected:
        return OperationalDecision(False, "FEED_DISCONNECTED")
    if state.clock_drift_ms > limits.max_clock_drift_ms:
        return OperationalDecision(False, "CLOCK_DRIFT_VETO")
    if state.unknown_order_state:
        return OperationalDecision(False, "UNKNOWN_ORDER_STATE")
    if state.duplicate_order_detected:
        return OperationalDecision(False, "DUPLICATE_ORDER_VETO")
    if state.position_mismatch_contracts > limits.max_position_mismatch_contracts:
        return OperationalDecision(False, "POSITION_RECONCILIATION_VETO")
    if state.recent_reject_rate > limits.max_reject_rate:
        return OperationalDecision(False, "REJECT_RATE_VETO")
    if state.observed_slippage_points > limits.max_slippage_points:
        return OperationalDecision(False, "SLIPPAGE_VETO")
    return OperationalDecision(True, "APPROVED")


def deterministic_order_key(*, signal_id: str, strategy_version: str, account: str, instrument: str, side: str) -> str:
    values = [signal_id, strategy_version, account, instrument, side]
    if any(not value or not value.strip() for value in values):
        raise ValueError("all order-key fields are required")
    if side not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    raw = "|".join(values).encode("utf-8")
    return sha256(raw).hexdigest()


class IdempotencyRegistry:
    """Process-local reference implementation; production storage must be durable."""

    def __init__(self) -> None:
        self._keys: set[str] = set()

    def register_once(self, key: str) -> bool:
        if not key.strip():
            raise ValueError("key is required")
        if key in self._keys:
            return False
        self._keys.add(key)
        return True
