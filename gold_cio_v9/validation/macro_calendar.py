"""Hash-bound point-in-time macro calendar for EXP-0001.

An empty list of macro events is not evidence that no events existed. Formal runs
therefore require an explicit source identity and coverage interval spanning the
research dataset. The canonical hash binds both coverage and every scheduled event.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timezone
from hashlib import sha256
import json
from typing import Sequence

from gold_cio_v9.data.governance import HistoricalBar
from gold_cio_v9.validation.exp0001_regimes import MacroEvent


@dataclass(frozen=True)
class MacroCalendarSnapshot:
    coverage_start: date
    coverage_end: date
    source_id: str
    events: tuple[MacroEvent, ...]
    calendar_hash: str


def _payload(*, coverage_start: date, coverage_end: date, source_id: str, events: Sequence[MacroEvent]) -> dict:
    if coverage_end < coverage_start:
        raise ValueError("macro calendar coverage_end precedes coverage_start")
    if not source_id.strip():
        raise ValueError("macro calendar source_id is required")
    ordered = tuple(sorted(events, key=lambda e: (e.event_time, e.category, e.known_at)))
    keys = [(e.event_time, e.category) for e in ordered]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate macro event identity")
    return {
        "coverage_start": coverage_start.isoformat(),
        "coverage_end": coverage_end.isoformat(),
        "source_id": source_id,
        "events": [
            {"event_time": e.event_time.isoformat(), "known_at": e.known_at.isoformat(), "category": e.category}
            for e in ordered
        ],
    }


def build_macro_calendar_snapshot(
    *,
    coverage_start: date,
    coverage_end: date,
    source_id: str,
    events: Sequence[MacroEvent],
) -> MacroCalendarSnapshot:
    payload = _payload(coverage_start=coverage_start, coverage_end=coverage_end, source_id=source_id, events=events)
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    ordered = tuple(sorted(events, key=lambda e: (e.event_time, e.category, e.known_at)))
    for event in ordered:
        day = event.event_time.astimezone(timezone.utc).date()
        if not coverage_start <= day <= coverage_end:
            raise ValueError("macro event falls outside declared calendar coverage")
    return MacroCalendarSnapshot(coverage_start, coverage_end, source_id, ordered, digest)


def validate_macro_calendar_for_bars(snapshot: MacroCalendarSnapshot, bars: Sequence[HistoricalBar]) -> None:
    if not bars:
        raise ValueError("bars are required for macro coverage validation")
    replay = build_macro_calendar_snapshot(
        coverage_start=snapshot.coverage_start,
        coverage_end=snapshot.coverage_end,
        source_id=snapshot.source_id,
        events=snapshot.events,
    )
    if replay.calendar_hash != snapshot.calendar_hash:
        raise ValueError("macro calendar hash mismatch")
    days = [b.event_time.astimezone(timezone.utc).date() for b in bars]
    if snapshot.coverage_start > min(days) or snapshot.coverage_end < max(days):
        raise ValueError("macro calendar does not cover the full evidence dataset")
