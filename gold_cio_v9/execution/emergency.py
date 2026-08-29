"""Human emergency controls with fail-closed semantics.

Human operators may reduce risk or flatten; they may not bypass hard risk limits.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EmergencyCommand(str, Enum):
    STOP_NEW_ORDERS = "STOP_NEW_ORDERS"
    CANCEL_ALL = "CANCEL_ALL"
    FLATTEN = "FLATTEN"
    SHADOW_ONLY = "SHADOW_ONLY"
    RESUME = "RESUME"


@dataclass(frozen=True)
class EmergencyState:
    kill_switch_active: bool
    reconciled: bool
    risk_limits_healthy: bool
    operator_authorized: bool


@dataclass(frozen=True)
class EmergencyDecision:
    allowed: bool
    reason: str


def authorize_emergency_command(command: EmergencyCommand, state: EmergencyState) -> EmergencyDecision:
    if not state.operator_authorized:
        return EmergencyDecision(False, "UNAUTHORIZED_OPERATOR")
    if command in {
        EmergencyCommand.STOP_NEW_ORDERS,
        EmergencyCommand.CANCEL_ALL,
        EmergencyCommand.FLATTEN,
        EmergencyCommand.SHADOW_ONLY,
    }:
        return EmergencyDecision(True, "RISK_REDUCING_COMMAND")
    if command is EmergencyCommand.RESUME:
        if state.kill_switch_active:
            return EmergencyDecision(False, "KILL_SWITCH_STILL_ACTIVE")
        if not state.reconciled:
            return EmergencyDecision(False, "STATE_NOT_RECONCILED")
        if not state.risk_limits_healthy:
            return EmergencyDecision(False, "RISK_LIMITS_NOT_HEALTHY")
        return EmergencyDecision(True, "RESUME_ALLOWED")
    return EmergencyDecision(False, "UNKNOWN_COMMAND")
