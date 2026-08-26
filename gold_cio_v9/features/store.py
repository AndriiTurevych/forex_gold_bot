"""Minimal point-in-time feature store with anti-lookahead guardrails."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping


def _require_aware(ts: datetime, name: str) -> None:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class FeatureRow:
    event_time: datetime
    available_time: datetime
    values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_aware(self.event_time, "event_time")
        _require_aware(self.available_time, "available_time")
        if self.available_time < self.event_time:
            raise ValueError("available_time cannot precede event_time")
        # Copy before freezing so caller-side mutations cannot rewrite history.
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


class PointInTimeFeatureStore:
    def __init__(self) -> None:
        self._rows: list[FeatureRow] = []

    def append(self, row: FeatureRow) -> None:
        if not isinstance(row, FeatureRow):
            raise TypeError("row must be a FeatureRow")
        self._rows.append(row)

    def snapshot(self, decision_time: datetime) -> list[FeatureRow]:
        """Return only observations that were actually available by decision_time."""
        _require_aware(decision_time, "decision_time")
        return [r for r in self._rows if r.available_time <= decision_time]

    def latest(self, decision_time: datetime) -> FeatureRow | None:
        """Return the newest event and, for revisions, newest available version."""
        rows = self.snapshot(decision_time)
        return max(rows, key=lambda r: (r.event_time, r.available_time)) if rows else None
