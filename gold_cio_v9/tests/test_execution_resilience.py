from pathlib import Path

import pytest

from gold_cio_v9.execution.broker_contract import BrokerOrderRequest, OrderType, TimeInForce
from gold_cio_v9.execution.journal import JournalEvent, SQLiteExecutionJournal, replay
from gold_cio_v9.execution.reconciliation import ReconciliationSnapshot, reconcile
from gold_cio_v9.execution.shadow_live import TwinFill, compare_shadow_live


def test_sqlite_journal_persists_and_replays(tmp_path: Path):
    path = tmp_path / "journal.db"
    journal = SQLiteExecutionJournal(path)
    assert journal.append("ORDER_SUBMITTED", {"id": "o1", "qty": 1}) == 1
    assert journal.append("ORDER_FILLED", {"id": "o1", "qty": 1}) == 2
    journal.close()

    reopened = SQLiteExecutionJournal(path)
    events = reopened.read_from()
    reopened.close()
    assert [e.event_type for e in events] == ["ORDER_SUBMITTED", "ORDER_FILLED"]
    state = replay(events, lambda s, e: s + [e.event_type], [])
    assert state == ["ORDER_SUBMITTED", "ORDER_FILLED"]


def test_replay_rejects_non_monotonic_sequence():
    events = [JournalEvent(2, "A", {}), JournalEvent(1, "B", {})]
    with pytest.raises(ValueError):
        replay(events, lambda s, e: s, None)


def test_reconciliation_fails_closed_on_position_mismatch():
    result = reconcile(
        ReconciliationSnapshot(
            local_position=0,
            broker_position=1,
            local_open_orders=frozenset(),
            broker_open_orders=frozenset(),
            local_cash=1000.0,
            broker_cash=1000.0,
        )
    )
    assert not result.reconciled
    assert result.reason == "POSITION_MISMATCH"


def test_reconciliation_detects_order_mismatch():
    result = reconcile(
        ReconciliationSnapshot(
            local_position=1,
            broker_position=1,
            local_open_orders=frozenset({"a"}),
            broker_open_orders=frozenset({"b"}),
            local_cash=1000.0,
            broker_cash=1000.0,
        )
    )
    assert not result.reconciled
    assert result.reason == "OPEN_ORDER_MISMATCH"


def test_shadow_live_detects_execution_divergence():
    shadow = TwinFill("sig", "BUY", 4700.0, 1)
    live = TwinFill("sig", "BUY", 4700.6, 1)
    result = compare_shadow_live(shadow, live, max_price_divergence_points=0.30)
    assert not result.matched
    assert result.reason == "PRICE_DIVERGENCE"


def test_shadow_live_matches_within_tolerance():
    shadow = TwinFill("sig", "SELL", 4700.0, 1)
    live = TwinFill("sig", "SELL", 4699.8, 1)
    result = compare_shadow_live(shadow, live, max_price_divergence_points=0.30)
    assert result.matched


def test_broker_contract_validates_stop_limit_prices():
    with pytest.raises(ValueError):
        BrokerOrderRequest(
            client_order_id="o1",
            instrument="GCZ6",
            side="BUY",
            quantity=1,
            order_type=OrderType.STOP_LIMIT,
            tif=TimeInForce.DAY,
            stop_price=4700.0,
        )


def test_broker_contract_accepts_market_order():
    order = BrokerOrderRequest(
        client_order_id="o1",
        instrument="GCZ6",
        side="SELL",
        quantity=1,
        order_type=OrderType.MARKET,
        tif=TimeInForce.DAY,
    )
    assert order.quantity == 1
