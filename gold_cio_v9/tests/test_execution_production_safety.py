from pathlib import Path

import pytest

from gold_cio_v9.execution.clock_health import ClockLimits, ClockSample, evaluate_clock
from gold_cio_v9.execution.durable_idempotency import (
    DurableIdempotencyStore,
    ReservationStatus,
)
from gold_cio_v9.execution.feed_health import FeedLimits, FeedSnapshot, evaluate_feed
from gold_cio_v9.execution.watchdog import ExecutionWatchdog, KillReason


def test_durable_idempotency_survives_restart(tmp_path: Path):
    path = tmp_path / "idem.sqlite"
    store = DurableIdempotencyStore(path)
    assert store.reserve_once("order-1")
    store.close()

    reopened = DurableIdempotencyStore(path)
    assert not reopened.reserve_once("order-1")
    assert reopened.get("order-1").status is ReservationStatus.RESERVED
    reopened.close()


def test_durable_idempotency_tracks_submitted_and_terminal(tmp_path: Path):
    store = DurableIdempotencyStore(tmp_path / "idem.sqlite")
    assert store.reserve_once("order-2")
    store.mark_submitted("order-2", "broker-77")
    item = store.get("order-2")
    assert item.status is ReservationStatus.SUBMITTED
    assert item.broker_order_id == "broker-77"
    store.mark_terminal("order-2")
    assert store.get("order-2").status is ReservationStatus.TERMINAL
    store.close()


def test_submitted_reservation_rejects_broker_id_change(tmp_path: Path):
    store = DurableIdempotencyStore(tmp_path / "idem.sqlite")
    store.reserve_once("order-3")
    store.mark_submitted("order-3", "broker-a")
    with pytest.raises(ValueError):
        store.mark_submitted("order-3", "broker-b")
    store.close()


def test_clock_requires_independent_sources():
    result = evaluate_clock(ClockSample(offset_ms=5, age_ms=100, jitter_ms=2, source_count=1))
    assert not result.healthy
    assert result.reason == "INSUFFICIENT_CLOCK_SOURCES"


def test_clock_fails_closed_on_offset_and_staleness():
    assert evaluate_clock(
        ClockSample(offset_ms=101, age_ms=100, jitter_ms=2, source_count=2),
        ClockLimits(max_abs_offset_ms=100),
    ).reason == "CLOCK_OFFSET_VETO"
    assert evaluate_clock(
        ClockSample(offset_ms=1, age_ms=2001, jitter_ms=2, source_count=2),
        ClockLimits(max_sample_age_ms=2000),
    ).reason == "CLOCK_SAMPLE_STALE"


def _feed(**overrides):
    base = dict(
        primary_bid=4700.0,
        primary_ask=4700.2,
        secondary_mid=4700.1,
        primary_age_ms=50.0,
        secondary_age_ms=60.0,
        sequence_gap=False,
        out_of_order=False,
    )
    base.update(overrides)
    return FeedSnapshot(**base)


def test_feed_healthy_when_fresh_and_agreed():
    result = evaluate_feed(_feed())
    assert result.healthy
    assert result.reason == "FEED_HEALTHY"


def test_feed_vetoes_gap_before_using_price():
    result = evaluate_feed(_feed(sequence_gap=True))
    assert not result.healthy
    assert result.reason == "SEQUENCE_GAP"


def test_feed_vetoes_cross_feed_disagreement():
    result = evaluate_feed(
        _feed(secondary_mid=4701.0), FeedLimits(max_cross_feed_diff_points=0.5)
    )
    assert not result.healthy
    assert result.reason == "CROSS_FEED_DISAGREEMENT"


def test_feed_vetoes_crossed_quote_and_stale_primary():
    assert evaluate_feed(_feed(primary_bid=4700.3, primary_ask=4700.2)).reason == "CROSSED_PRIMARY_QUOTE"
    assert evaluate_feed(_feed(primary_age_ms=501), FeedLimits(max_age_ms=500)).reason == "PRIMARY_FEED_STALE"


def test_watchdog_latches_multiple_reasons_and_does_not_auto_reset():
    watchdog = ExecutionWatchdog()
    watchdog.trip(KillReason.FEED)
    watchdog.trip(KillReason.RECONCILIATION)
    status = watchdog.status
    assert status.killed
    assert set(status.reasons) == {KillReason.FEED, KillReason.RECONCILIATION}
    with pytest.raises(ValueError):
        watchdog.reset(
            reconciled=False,
            risk_healthy=True,
            feed_healthy=True,
            clock_healthy=True,
            broker_connected=True,
        )
    assert watchdog.status.killed


def test_watchdog_requires_full_health_for_explicit_reset():
    watchdog = ExecutionWatchdog()
    watchdog.trip(KillReason.INTERNAL_ERROR)
    status = watchdog.reset(
        reconciled=True,
        risk_healthy=True,
        feed_healthy=True,
        clock_healthy=True,
        broker_connected=True,
    )
    assert not status.killed
    assert status.reasons == ()
