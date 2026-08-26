"""Point-in-time ICT event models with explicit confirmation availability.

ICT structures are often only knowable after later bars confirm them. These models
separate where an event occurred (event_time) from when the trading system was
allowed to know it (available_time). State changes are append-only revisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


def _aware(ts: datetime, field: str) -> None:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


@dataclass(frozen=True)
class ConfirmedSwing:
    kind: Literal["HIGH", "LOW"]
    price: float
    event_time: datetime
    available_time: datetime
    left_bars: int
    right_bars: int

    def __post_init__(self) -> None:
        _aware(self.event_time, "event_time")
        _aware(self.available_time, "available_time")
        if self.available_time <= self.event_time:
            raise ValueError("swing must become available strictly after event_time")
        if self.left_bars < 1 or self.right_bars < 1:
            raise ValueError("swing confirmation requires positive left/right bars")


@dataclass(frozen=True)
class FVGStateRevision:
    fvg_id: str
    direction: Literal["BULLISH", "BEARISH"]
    lower: float
    upper: float
    event_time: datetime
    available_time: datetime
    state: Literal["OPEN", "PARTIALLY_FILLED", "FILLED", "INVALIDATED"]
    revision: int

    def __post_init__(self) -> None:
        _aware(self.event_time, "event_time")
        _aware(self.available_time, "available_time")
        if self.available_time < self.event_time:
            raise ValueError("available_time cannot precede event_time")
        if self.upper <= self.lower:
            raise ValueError("FVG upper must exceed lower")
        if self.revision < 0:
            raise ValueError("revision must be non-negative")


def latest_revision_as_of(revisions: list[FVGStateRevision], decision_time: datetime) -> FVGStateRevision | None:
    """Return only the FVG state version knowable at decision_time."""
    _aware(decision_time, "decision_time")
    visible = [r for r in revisions if r.available_time <= decision_time]
    return max(visible, key=lambda r: (r.available_time, r.revision)) if visible else None
