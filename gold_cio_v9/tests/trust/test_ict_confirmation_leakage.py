from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.ict_engine.pit_events import ConfirmedSwing, FVGStateRevision, latest_revision_as_of

UTC = timezone.utc


def test_swing_cannot_be_available_at_its_own_bar():
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="strictly after event_time"):
        ConfirmedSwing("HIGH", 4500.0, t0, t0, 2, 2)


def test_confirmed_swing_is_delayed_until_confirmation_bar():
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    t2 = t0 + timedelta(minutes=10)
    swing = ConfirmedSwing("HIGH", 4500.0, t0, t2, 2, 2)
    assert swing.available_time > swing.event_time


def test_fvg_future_fill_state_is_not_visible_early():
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    t1 = t0 + timedelta(minutes=5)
    t3 = t0 + timedelta(minutes=15)
    revisions = [
        FVGStateRevision("fvg-1", "BULLISH", 4490.0, 4495.0, t0, t1, "OPEN", 0),
        FVGStateRevision("fvg-1", "BULLISH", 4490.0, 4495.0, t0, t3, "FILLED", 1),
    ]
    as_of_t1 = latest_revision_as_of(revisions, t1)
    assert as_of_t1 is not None
    assert as_of_t1.state == "OPEN"

    as_of_t3 = latest_revision_as_of(revisions, t3)
    assert as_of_t3 is not None
    assert as_of_t3.state == "FILLED"


def test_fvg_state_history_is_append_only_by_revision():
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    revisions = [
        FVGStateRevision("fvg-1", "BEARISH", 4505.0, 4510.0, t0, t0, "OPEN", 0),
        FVGStateRevision("fvg-1", "BEARISH", 4505.0, 4510.0, t0, t0 + timedelta(minutes=5), "PARTIALLY_FILLED", 1),
        FVGStateRevision("fvg-1", "BEARISH", 4505.0, 4510.0, t0, t0 + timedelta(minutes=10), "FILLED", 2),
    ]
    assert [r.revision for r in revisions] == [0, 1, 2]
    assert [r.state for r in revisions] == ["OPEN", "PARTIALLY_FILLED", "FILLED"]
