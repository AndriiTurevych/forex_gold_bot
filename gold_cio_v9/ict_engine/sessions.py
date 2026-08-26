"""Session-liquidity helpers for point-in-time ICT research.

All timestamps must be timezone-aware before entering this module.
Session windows are configurable research definitions, not claims of canonical ICT rules.
"""
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Iterable, Optional


@dataclass(frozen=True)
class SessionWindow:
    name: str
    start: time
    end: time


@dataclass(frozen=True)
class SessionLiquidity:
    name: str
    session_date: date
    high: float
    low: float
    high_ts: datetime
    low_ts: datetime


def _require_aware(ts: datetime) -> None:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("session timestamps must be timezone-aware")


def in_window(ts: datetime, window: SessionWindow) -> bool:
    _require_aware(ts)
    t = ts.timetz().replace(tzinfo=None)
    if window.start <= window.end:
        return window.start <= t < window.end
    return t >= window.start or t < window.end


def session_liquidity(
    rows: Iterable[tuple[datetime, float, float]],
    window: SessionWindow,
    session_date: date,
) -> Optional[SessionLiquidity]:
    """Calculate one session's high/low without leaking observations from other dates."""
    selected: list[tuple[datetime, float, float]] = []
    for ts, high, low in rows:
        _require_aware(ts)
        if ts.date() == session_date and in_window(ts, window):
            selected.append((ts, high, low))
    if not selected:
        return None
    high_row = max(selected, key=lambda x: x[1])
    low_row = min(selected, key=lambda x: x[2])
    return SessionLiquidity(window.name, session_date, high_row[1], low_row[2], high_row[0], low_row[0])


# Research defaults expressed in the timezone of incoming data.
# Production adapters must convert source timestamps to an explicitly configured session timezone.
DEFAULT_WINDOWS = {
    "ASIA": SessionWindow("ASIA", time(0, 0), time(6, 0)),
    "LONDON": SessionWindow("LONDON", time(7, 0), time(10, 0)),
    "NY_AM": SessionWindow("NY_AM", time(13, 30), time(16, 0)),
}
