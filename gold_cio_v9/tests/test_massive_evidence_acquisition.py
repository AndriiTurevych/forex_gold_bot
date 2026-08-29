from datetime import date, datetime, timezone

from gold_cio_v9.data.contract_master import build_gc_contract_master
from gold_cio_v9.data.massive_evidence_acquisition import (
    acquire_exp0001_massive_evidence,
    derive_trading_dates_and_prior_map,
    fetch_all_pages,
)


def _master():
    return build_gc_contract_master((
        {"ticker":"GCM5","product_code":"GC","first_trade_date":"2024-01-01","last_trade_date":"2025-06-26","settlement_date":"2025-06-26"},
        {"ticker":"GCQ5","product_code":"GC","first_trade_date":"2024-01-01","last_trade_date":"2025-08-27","settlement_date":"2025-08-27"},
    ))


def _ns(y, m, d, hh):
    return int(datetime(y, m, d, hh, tzinfo=timezone.utc).timestamp() * 1_000_000_000)


def _session(ticker, d, volume):
    return {"ticker": ticker, "window_start": _ns(d.year, d.month, d.day, 0), "session_end_date": d.isoformat(), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": volume}


def _minute(ticker, event_day, session_day, px):
    return {
        "ticker": ticker, "window_start": _ns(event_day.year, event_day.month, event_day.day, 22),
        "session_end_date": session_day.isoformat(), "open": px, "high": px + 1.0,
        "low": px - 1.0, "close": px + 0.5, "volume": 10.0,
    }


def test_fetch_all_pages_follows_cursor_once_and_preserves_completion():
    calls = []
    def get(target, params):
        calls.append((target, dict(params)))
        if len(calls) == 1:
            return {"status": "OK", "results": [{"x": 1}], "next_url": "https://api.massive.com/next?cursor=abc"}
        return {"status": "OK", "results": [{"x": 2}]}
    pages = fetch_all_pages(get, path="/x", params={"a": 1})
    assert len(pages) == 2
    assert calls[0] == ("/x", {"a": 1})
    assert calls[1] == ("https://api.massive.com/next?cursor=abc", {})


def test_trading_dates_are_observed_sessions_with_strict_prior_mapping():
    histories = {
        "GCM5": {date(2025,5,30): {}, date(2025,6,2): {}, date(2025,6,3): {}},
        "GCQ5": {date(2025,6,2): {}, date(2025,6,3): {}},
    }
    dates, prior = derive_trading_dates_and_prior_map(
        histories, coverage_start=date(2025,6,2), coverage_end=date(2025,6,3),
    )
    assert dates == (date(2025,6,2), date(2025,6,3))
    assert prior[date(2025,6,2)] == date(2025,5,30)
    assert prior[date(2025,6,3)] == date(2025,6,2)


def test_end_to_end_acquisition_selects_prior_session_volume_and_keeps_prior_evening_bars():
    s0, d1, d2 = date(2025,5,30), date(2025,6,2), date(2025,6,3)
    session_rows = {
        "GCM5": [_session("GCM5", s0, 200.0), _session("GCM5", d1, 50.0), _session("GCM5", d2, 20.0)],
        "GCQ5": [_session("GCQ5", s0, 100.0), _session("GCQ5", d1, 300.0), _session("GCQ5", d2, 400.0)],
    }
    minute_rows = {
        "GCM5": [_minute("GCM5", date(2025,6,1), d1, 3300.0)],
        "GCQ5": [_minute("GCQ5", date(2025,6,2), d2, 3310.0)],
    }

    def get(target, params):
        ticker = target.rstrip("/").split("/")[-1]
        resolution = params.get("resolution")
        if resolution == "1session":
            return {"status": "OK", "request_id": f"s-{ticker}", "results": session_rows[ticker]}
        if resolution == "1min":
            return {"status": "OK", "request_id": f"m-{ticker}", "results": minute_rows[ticker]}
        raise AssertionError((target, params))

    result = acquire_exp0001_massive_evidence(
        get, master=_master(), coverage_start=d1, coverage_end=d2,
    )
    assert result.dataset.manifest.contracts == ("GCM5", "GCQ5")
    assert len(result.dataset.bars) == 2
    assert result.dataset.bars[0].event_time.date() == date(2025,6,1)
    assert result.dataset.bars[0].contract == "GCM5"
    assert result.dataset.bars[1].event_time.date() == date(2025,6,2)
    assert result.dataset.bars[1].contract == "GCQ5"
    assert all(not b.is_roll_window for b in result.dataset.bars)
    assert result.lineage.roll_buffer_bars == 0
    assert result.lineage.contract_master_hash == _master().master_hash
    assert result.lineage.decisions[0].selected_contract == "GCM5"
    assert result.lineage.decisions[1].selected_contract == "GCQ5"
