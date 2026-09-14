from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.data.binance_paxg import (
    evaluate_proxy_readiness,
    parse_book_ticker,
    parse_klines,
)


NOW = datetime(2026, 9, 14, 17, 4, 30, tzinfo=timezone.utc)


def _ms(value):
    return int(value.timestamp() * 1000)


def _quote(bid="4319.81", ask="4319.82", symbol="PAXGUSDT"):
    return {"symbol": symbol, "bidPrice": bid, "askPrice": ask}


def _bar(*, opened=None, closed=None, low="4319.49", high="4321.12"):
    opened = opened or NOW - timedelta(minutes=1, seconds=30)
    closed = closed or NOW - timedelta(seconds=30)
    return [
        _ms(opened), "4321.12", high, low, "4319.97", "2.2488",
        _ms(closed), "9715.25", 27, "0.428", "1848.91", "0",
    ]


def test_fresh_public_proxy_is_data_ready_but_never_gc_or_execution_evidence():
    result = evaluate_proxy_readiness(
        quote_payload=_quote(), kline_rows=[_bar()], acquired_at=NOW
    )
    assert result["status"] == "DATA_READY"
    assert result["instrument_role"] == "GOLD_PROXY_ONLY"
    assert result["quote_timestamp_quality"] == "RECEIPT_TIME_ONLY"
    assert result["formal_gc_verdict_allowed"] is False
    assert result["real_orders_allowed"] is False
    assert result["strategy_outcomes_generated"] is False


def test_stale_closed_bar_forces_veto():
    result = evaluate_proxy_readiness(
        quote_payload=_quote(),
        kline_rows=[_bar(
            opened=NOW - timedelta(minutes=5),
            closed=NOW - timedelta(minutes=4),
        )],
        acquired_at=NOW,
    )
    assert result["data_ready"] is False
    assert "STALE_BAR_VETO" in result["reasons"]


def test_current_incomplete_bar_is_not_treated_as_closed():
    result = evaluate_proxy_readiness(
        quote_payload=_quote(),
        kline_rows=[_bar(opened=NOW, closed=NOW + timedelta(seconds=59))],
        acquired_at=NOW,
    )
    assert result["data_ready"] is False
    assert result["reasons"] == ["NO_CLOSED_BAR"]


def test_wide_spread_forces_veto():
    result = evaluate_proxy_readiness(
        quote_payload=_quote(bid="4300", ask="4310"),
        kline_rows=[_bar()],
        acquired_at=NOW,
    )
    assert "WIDE_SPREAD_VETO" in result["reasons"]


def test_symbol_identity_and_quote_integrity_fail_closed():
    with pytest.raises(ValueError, match="SYMBOL_MISMATCH"):
        parse_book_ticker(_quote(symbol="GCZ6"), acquired_at=NOW)
    with pytest.raises(ValueError, match="CROSSED"):
        parse_book_ticker(_quote(bid="4320", ask="4319"), acquired_at=NOW)


def test_kline_duplicate_and_ohlc_corruption_are_rejected():
    bar = _bar()
    with pytest.raises(ValueError, match="DUPLICATE"):
        parse_klines([bar, bar])
    corrupt = _bar(high="4300")
    with pytest.raises(ValueError, match="INVALID_OHLC"):
        parse_klines([corrupt])


def test_snapshot_hash_is_deterministic():
    first = evaluate_proxy_readiness(
        quote_payload=_quote(), kline_rows=[_bar()], acquired_at=NOW
    )
    second = evaluate_proxy_readiness(
        quote_payload=_quote(), kline_rows=[_bar()], acquired_at=NOW
    )
    assert first["snapshot_hash"] == second["snapshot_hash"]
