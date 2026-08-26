"""Session-liquidity helpers for point-in-time ICT research.

All timestamps must be timezone-aware before entering this module.
Session windows are configurable research definitions, not claims of canonical ICT rules.
When a timezone_name is configured, timestamps are converted into that IANA timezone
before session membership is evaluated, making DST transitions explicit and reproducible.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import isfinite
from typing import Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class SessionWindow:
    name: str
    start: time
    end: time
    timezone_name: str | None = None

    def __post_init__(self) -> None:
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise ValueError("session start/end must be naive wall-clock times")
        if self.timezone_name is not None:
            try:
                ZoneInfo(self.timezone_name)
            except ZoneInfoNotFoundError as exc:
                raise ValueError(f"unknown session timezone: {self.timezone_name}") from exc


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


def _as_session_time(ts: datetime, window: SessionWindow) -> datetime:
    _require_aware(ts)
    if window.timezone_name is None:
        return ts
    return ts.astimezone(ZoneInfo(window.timezone_name))


def in_window(ts: datetime, window: SessionWindow) -> bool:
    local_ts = _as_session_time(ts, window)
    t = local_ts.timetz().replace(tzinfo=None)
    if window.start <= window.end:
        return window.start <= t < window.end
    return t >= window.start or t < window.end


def _belongs_to_session_date(ts: datetime, window: SessionWindow, session_date: date) -> bool:
    """Treat session_date as the date on which the configured session starts."""
    local_ts = _as_session_time(ts, window)
    t = local_ts.timetz().replace(tzinfo=None)
    if window.start <= window.end:
        return local_ts.date() == session_date and window.start <= t < window.end
    if local_ts.date() == session_date:
        return t >= window.start
    if local_ts.date() == session_date + timedelta(days=1):
        return t < window.end
    return False


def session_liquidity(
    rows: Iterable[tuple[datetime, float, float]],
    window: SessionWindow,
    session_date: date,
) -> Optional[SessionLiquidity]:
    """Calculate one session's high/low without leaking observations from other sessions."""
    selected: list[tuple[datetime, float, float]] = []
    for ts, high, low in rows:
        _require_aware(ts)
        if not (isfinite(high) and isfinite(low)):
            raise ValueError("session high/low must be finite")
        if high < low:
            raise ValueError("session high cannot be below low")
        if _belongs_to_session_date(ts, window, session_date):
            selected.append((ts, high, low))
    if not selected:
        return None
    high_row = max(selected, key=lambda x: x[1])
    low_row = min(selected, key=lambda x: x[2])
    return SessionLiquidity(window.name, session_date, high_row[1], low_row[2], high_row[0], low_row[0])


# Deterministic research defaults. Their wall-clock convention is explicitly UTC
# so identical source observations produce identical session membership regardless
# of the timezone used by an upstream data feed. Experiments may override these
# with named local-market timezones (e.g. America/New_York) when required.
DEFAULT_WINDOWS = {
    "ASIA": SessionWindow("ASIA", time(0, 0), time(6, 0), "UTC"),
    "LONDON": SessionWindow("LONDON", time(7, 0), time(10, 0), "UTC"),
    "NY_AM": SessionWindow("NY_AM", time(13, 30), time(16, 0), "UTC"),
}
