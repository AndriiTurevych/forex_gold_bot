from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from gold_cio_v9.data.mt5_snapshot import SCHEMA, seal, validate_snapshot
from scripts.collect_mt5_xauusd import collect


NOW = datetime(2026, 9, 14, 12, 0, 8, tzinfo=timezone.utc)


def snapshot(**changes):
    payload = {
        "schema": SCHEMA, "source": "MT5_BROKER_TERMINAL",
        "purpose": "OUTCOME_FREE_BROKER_FEED_PREFLIGHT",
        "acquired_at": NOW.isoformat(),
        "instrument": {"symbol": "XAUUSD", "point": .01},
        "quote": {"event_time": (NOW - timedelta(seconds=2)).isoformat(), "bid": 4329.68, "ask": 4329.88},
        "timeframe": "M1_CLOSED_ONLY",
        "m1_bars": [{
            "event_time": (NOW.replace(second=0) - timedelta(minutes=m)).isoformat(),
            "open": 4329., "high": 4331., "low": 4328., "close": 4330.,
            "tick_volume": 10, "spread_points": 20, "real_volume": 0,
        } for m in (2, 1)],
        "identity_redaction": "NO_ACCOUNT_LOGIN_NO_ACCOUNT_NAME_NO_SERVER",
        "instrument_separation": "BROKER_XAUUSD_NOT_COMEX_GC",
        "real_orders_allowed": False,
    }
    payload.update(changes)
    return seal(payload)


def test_fresh_sealed_snapshot_is_ready():
    result = validate_snapshot(snapshot(), observed_at=NOW, expected_symbol="XAUUSD")
    assert result.broker_feed_ready is True
    assert result.reason == "BROKER_FEED_READY"
    assert result.spread_price == pytest.approx(.20)
    assert result.real_orders_allowed is False


@pytest.mark.parametrize("change,reason", [
    ({"real_orders_allowed": True}, "ORDER_PERMISSION_VETO"),
    ({"schema": "other"}, "SCHEMA_MISMATCH"),
    ({"quote": {"event_time": NOW.isoformat(), "bid": 10, "ask": 9}}, "CROSSED_QUOTE"),
    ({"quote": {"event_time": NOW.isoformat(), "bid": 10, "ask": 13}}, "ABNORMAL_SPREAD"),
])
def test_fail_closed_contract(change, reason):
    result = validate_snapshot(snapshot(**change), observed_at=NOW)
    assert result.broker_feed_ready is False and result.reason == reason


def test_tampering_and_staleness_are_vetoed():
    tampered = snapshot()
    tampered["quote"]["bid"] = 1
    assert validate_snapshot(tampered, observed_at=NOW).reason == "SNAPSHOT_HASH_MISMATCH"
    old = NOW - timedelta(seconds=11)
    payload = snapshot(quote={"event_time": old.isoformat(), "bid": 4329.68, "ask": 4329.88})
    assert validate_snapshot(payload, observed_at=NOW).reason == "STALE_QUOTE_VETO"


def test_symbol_and_bar_order_cannot_be_mixed():
    assert validate_snapshot(snapshot(), observed_at=NOW, expected_symbol="GOLD").reason == "SYMBOL_MISMATCH"
    bars = snapshot()["m1_bars"]
    payload = snapshot(m1_bars=list(reversed(bars)))
    assert validate_snapshot(payload, observed_at=NOW).reason == "DUPLICATE_OR_UNSORTED_BAR"


def test_collector_redacts_identity_and_never_routes_orders(monkeypatch):
    monkeypatch.setattr("scripts.collect_mt5_xauusd.datetime", SimpleNamespace(
        now=lambda tz: NOW, fromtimestamp=datetime.fromtimestamp))
    rates = [
        {"time": int((NOW.replace(second=0) - timedelta(minutes=m)).timestamp()),
         "open": 10., "high": 12., "low": 9., "close": 11.,
         "tick_volume": 5, "spread": 20, "real_volume": 0}
        for m in (1, 2)
    ]
    class MT5:
        TIMEFRAME_M1 = 1
        def initialize(self, **kwargs): return True
        def shutdown(self): pass
        def last_error(self): return None
        def terminal_info(self): return SimpleNamespace(connected=True)
        def symbol_select(self, symbol, enabled): return True
        def symbol_info(self, symbol):
            return SimpleNamespace(digits=2, point=.01, trade_tick_size=.01,
                                   trade_contract_size=100, volume_min=.01,
                                   volume_max=100, volume_step=.01, currency_profit="USD")
        def symbol_info_tick(self, symbol):
            return SimpleNamespace(time_msc=int((NOW - timedelta(seconds=1)).timestamp() * 1000),
                                   bid=10., ask=10.2, last=0., volume_real=0., flags=6)
        def copy_rates_from_pos(self, symbol, timeframe, start, count): return rates
    result = collect(MT5(), symbol="XAUUSD", bar_count=120)
    assert result["real_orders_allowed"] is False
    assert result["identity_redaction"].startswith("NO_ACCOUNT")
    assert not ({"account", "login", "name", "server"} & result.keys())
    assert [r["event_time"] for r in result["m1_bars"]] == sorted(r["event_time"] for r in result["m1_bars"])
