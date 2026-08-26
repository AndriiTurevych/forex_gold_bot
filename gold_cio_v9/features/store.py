"""Minimal point-in-time feature store with anti-lookahead guardrails."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FeatureRow:
    event_time: datetime
    available_time: datetime
    values: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.available_time < self.event_time:
            raise ValueError("available_time cannot precede event_time")


class PointInTimeFeatureStore:
    def __init__(self) -> None:
        self._rows: list[FeatureRow] = []

    def append(self, row: FeatureRow) -> None:
        self._rows.append(row)

    def snapshot(self, decision_time: datetime) -> list[FeatureRow]:
        """Return only observations that were actually available by decision_time."""
        return [r for r in self._rows if r.available_time <= decision_time]

    def latest(self, decision_time: datetime) -> FeatureRow | None:
        rows = self.snapshot(decision_time)
        return max(rows, key=lambda r: r.event_time) if rows else None
