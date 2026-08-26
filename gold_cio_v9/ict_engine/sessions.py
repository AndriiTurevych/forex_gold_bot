"""Session-liquidity helpers for point-in-time ICT research.

All timestamps are expected to be timezone-aware before entering this module.
Session windows are intentionally configurable; defaults are research defaults,
not claims of canonical ICT definitions.
"""
from dataclasses import dataclass
from datetime import datetime, time
from typing import Iterable, Optional


@dataclass(frozen=True)
class SessionWindow:
    name: str
    start: time
    end: time


@dataclass(frozen=True)
class SessionLiquidity:
    name: str
    high: float
    low: float
    high_ts: datetime
    low_ts: datetime


def in_window(ts: datetime, window: SessionWindow) -> bool:
    t = ts.timetz().replace(tzinfo=None)
    if window.start <= window.end:
        return window.start <= t < window.end
    return t >= window.start or t < window.end


def session_liquidity(rows: Iterable[tuple[datetime, float, float]], window: SessionWindow) -> Optional[SessionLiquidity]:
    selected = [(ts, high, low) for ts, high, low in rows if in_window(ts, window)]
    if not selected:
        return None
    high_row = max(selected, key=lambda x: x[1])
    low_row = min(selected, key=lambda x: x[2])
    return SessionLiquidity(window.name, high_row[1], low_row[2], high_row[0], low_row[0])


DEFAULT_WINDOWS = {
    "ASIA": SessionWindow("ASIA", time(0, 0), time(6, 0)),
    "LONDON": SessionWindow("LONDON", time(7, 0), time(10, 0)),
    "NY_AM": SessionWindow("NY_AM", time(13, 30), time(16, 0)),
}
