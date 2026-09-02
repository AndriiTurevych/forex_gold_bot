"""Independent latching watchdog for production execution safety."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class KillReason(str, Enum):
    MANUAL = "MANUAL"
    FEED = "FEED"
    CLOCK = "CLOCK"
    BROKER = "BROKER"
    RECONCILIATION = "RECONCILIATION"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    RISK = "RISK"
    EXECUTION_QUALITY = "EXECUTION_QUALITY"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class WatchdogStatus:
    killed: bool
    reasons: tuple[KillReason, ...]


@dataclass
class ExecutionWatchdog:
    """Kill state is latched until explicit safe reset; no automatic unkill."""

    _reasons: set[KillReason] = field(default_factory=set)

    @property
    def status(self) -> WatchdogStatus:
        return WatchdogStatus(bool(self._reasons), tuple(sorted(self._reasons, key=lambda r: r.value)))

    def trip(self, reason: KillReason) -> WatchdogStatus:
        if not isinstance(reason, KillReason):
            raise ValueError("valid KillReason required")
        self._reasons.add(reason)
        return self.status

    def reset(self, *, reconciled: bool, risk_healthy: bool, feed_healthy: bool, clock_healthy: bool, broker_connected: bool) -> WatchdogStatus:
        if not all(isinstance(v, bool) for v in (reconciled, risk_healthy, feed_healthy, clock_healthy, broker_connected)):
            raise ValueError("reset health inputs must be boolean")
        if not (reconciled and risk_healthy and feed_healthy and clock_healthy and broker_connected):
            raise ValueError("cannot reset watchdog while system is not fully healthy")
        self._reasons.clear()
        return self.status
