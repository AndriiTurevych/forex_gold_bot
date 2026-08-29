from datetime import date
from pathlib import Path

from gold_cio_v9.validation.evidence_inputs import load_macro_calendar_json


CALENDAR = Path("gold_cio_v9/experiments/EXP-0001-macro-calendar-official-v1.json")


def test_official_macro_calendar_is_causal_and_covers_evidence_period():
    snapshot = load_macro_calendar_json(CALENDAR)
    assert snapshot.coverage_start == date(2025, 4, 3)
    assert snapshot.coverage_end == date(2026, 8, 27)
    assert snapshot.source_id.startswith("official:")
    assert len(snapshot.events) == 43
    assert {event.category for event in snapshot.events} == {"FOMC", "CPI", "NFP"}
    assert all(event.known_at <= event.event_time for event in snapshot.events)
    identities = {(event.event_time, event.category) for event in snapshot.events}
    assert len(identities) == len(snapshot.events)


def test_macro_calendar_has_events_in_both_evidence_years():
    snapshot = load_macro_calendar_json(CALENDAR)
    years = {event.event_time.year for event in snapshot.events}
    assert years == {2025, 2026}
