from datetime import date, datetime, timezone

import pytest

from gold_cio_v9.data.evidence_dataset_pipeline import (
    assemble_evidence_dataset,
    build_calendar_from_liquidity_responses,
    build_liquid_contract_fetch_plan,
    build_liquidity_request_plan,
)


def meta(ticker, as_of, settlement, last_trade):
    return {
        "ticker": ticker,
        "product_code": "GC",
        "active": True,
        "date": as_of.isoformat(),
        "first_trade_date": "2024-01-01",
        "last_trade_date": last_trade,
        "settlement_date": settlement,
    }


def session_row(ticker, session_date, volume):
    return {"ticker": ticker, "session_end_date": session_date.isoformat(), "volume": volume}


def ns(y, m, d, hh=12, mm=0):
    return int(datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timestamp() * 1_000_000_000)


def bar(ticker, timestamp, px, session_date):
    return {
        "ticker": ticker,
        "window_start": timestamp,
        "session_end_date": session_date.isoformat(),
        "open": px,
        "high": px + 1.0,
        "low": px - 1.0,
        "close": px + 0.5,
        "volume": 100.0,
    }


def two_day_inputs():
    d1, d2 = date(2025, 6, 2), date(2025, 6, 3)
    s1, s2 = date(2025, 5, 30), date(2025, 6, 2)
    snapshots = {
        d1: [
            meta("GCM5", d1, "2025-06-27", "2025-06-27"),
            meta("GCQ5", d1, "2025-08-27", "2025-08-27"),
        ],
        d2: [
            meta("GCM5", d2, "2025-06-27", "2025-06-27"),
            meta("GCQ5", d2, "2025-08-27", "2025-08-27"),
        ],
    }
    prior_dates = {d1: s1, d2: s2}
    responses = {
        d1: {
            "GCM5": [session_row("GCM5", s1, 1240)],
            "GCQ5": [session_row("GCQ5", s1, 179229)],
        },
        d2: {
            "GCM5": [session_row("GCM5", s2, 1000)],
            "GCQ5": [session_row("GCQ5", s2, 180000)],
        },
    }
    return d1, d2, snapshots, prior_dates, responses


def _q_pages(d1, d2):
    return {"GCQ5": [{"request_id": "p1", "results": [
        # First assigned Monday session opens Sunday UTC and must be retained.
        bar("GCQ5", ns(2025, 6, 1, 22), 3298.0, d1),
        bar("GCQ5", ns(2025, 6, 2, 12), 3300.0, d1),
        bar("GCQ5", ns(2025, 6, 2, 22), 3308.0, d2),
        bar("GCQ5", ns(2025, 6, 3, 12), 3310.0, d2),
        # Query padding on end_date can contain the next session; it must be dropped.
        bar("GCQ5", ns(2025, 6, 3, 22), 3320.0, date(2025, 6, 4)),
    ]}]}


def test_full_causal_pipeline_freezes_session_correct_manifest_hash():
    d1, d2, snapshots, prior_dates, responses = two_day_inputs()
    requests = build_liquidity_request_plan(snapshots, dates=[d1, d2], prior_session_date_by_as_of=prior_dates)
    calendar = build_calendar_from_liquidity_responses(snapshots, requests=requests, responses_by_as_of=responses)
    assert calendar.contract_order == ("GCQ5",)
    assert [d.contract for d in calendar.days] == ["GCQ5", "GCQ5"]

    pages = _q_pages(d1, d2)
    result1 = assemble_evidence_dataset(calendar, pages_by_contract=pages)
    result2 = assemble_evidence_dataset(calendar, pages_by_contract=pages)
    assert result1.manifest.dataset_hash == result2.manifest.dataset_hash
    assert result1.manifest.rows == 4
    assert result1.bars[0].event_time.date() == date(2025, 6, 1)
    assert result1.bars[-1].event_time.date() == date(2025, 6, 3)
    assert result1.manifest.contracts == ("GCQ5",)
    assert result1.fetch_windows[0].start_date == d1
    assert result1.fetch_windows[0].end_date == d2
    assert result1.fetch_windows[0].query_window_start_gte == date(2025, 6, 1)


def test_manifest_hash_changes_when_authoritative_bar_changes():
    d1, d2, snapshots, prior_dates, responses = two_day_inputs()
    requests = build_liquidity_request_plan(snapshots, dates=[d1, d2], prior_session_date_by_as_of=prior_dates)
    calendar = build_calendar_from_liquidity_responses(snapshots, requests=requests, responses_by_as_of=responses)
    base = {"GCQ5": [{"results": [
        bar("GCQ5", ns(2025, 6, 1, 22), 3300.0, d1),
        bar("GCQ5", ns(2025, 6, 2, 22), 3310.0, d2),
    ]}]}
    changed = {"GCQ5": [{"results": [
        bar("GCQ5", ns(2025, 6, 1, 22), 3300.0, d1),
        bar("GCQ5", ns(2025, 6, 2, 22), 3311.0, d2),
    ]}]}
    a = assemble_evidence_dataset(calendar, pages_by_contract=base)
    b = assemble_evidence_dataset(calendar, pages_by_contract=changed)
    assert a.manifest.dataset_hash != b.manifest.dataset_hash


def test_liquidity_request_plan_requires_explicit_prior_trading_session():
    d1, _, snapshots, _, _ = two_day_inputs()
    with pytest.raises(ValueError, match="missing prior session date"):
        build_liquidity_request_plan(snapshots, dates=[d1], prior_session_date_by_as_of={})


def test_request_plan_rejects_future_or_same_day_liquidity():
    d1, _, snapshots, _, _ = two_day_inputs()
    with pytest.raises(ValueError, match="strictly before"):
        build_liquidity_request_plan(snapshots, dates=[d1], prior_session_date_by_as_of={d1: d1})


def test_calendar_fails_closed_on_missing_contract_liquidity_response():
    d1, _, snapshots, prior_dates, responses = two_day_inputs()
    requests = build_liquidity_request_plan(snapshots, dates=[d1], prior_session_date_by_as_of={d1: prior_dates[d1]})
    broken = {d1: {"GCQ5": responses[d1]["GCQ5"]}}
    with pytest.raises(ValueError, match="missing completed liquidity response for GCM5"):
        build_calendar_from_liquidity_responses(snapshots, requests=requests, responses_by_as_of=broken)


def test_fetch_plan_tracks_roll_without_reentry():
    d1, d2, snapshots, prior_dates, responses = two_day_inputs()
    responses[d1]["GCM5"][0]["volume"] = 200000
    responses[d1]["GCQ5"][0]["volume"] = 100000
    requests = build_liquidity_request_plan(snapshots, dates=[d1, d2], prior_session_date_by_as_of=prior_dates)
    calendar = build_calendar_from_liquidity_responses(snapshots, requests=requests, responses_by_as_of=responses)
    windows = build_liquid_contract_fetch_plan(calendar)
    assert [(w.contract, w.start_date, w.end_date) for w in windows] == [("GCM5", d1, d1), ("GCQ5", d2, d2)]
    assert windows[0].query_window_start_gte == date(2025, 6, 1)
    assert windows[1].query_window_start_gte == date(2025, 6, 2)


def test_evidence_assembly_rejects_incomplete_pagination():
    d1, d2, snapshots, prior_dates, responses = two_day_inputs()
    requests = build_liquidity_request_plan(snapshots, dates=[d1, d2], prior_session_date_by_as_of=prior_dates)
    calendar = build_calendar_from_liquidity_responses(snapshots, requests=requests, responses_by_as_of=responses)
    pages = {"GCQ5": [{"next_url": "still-more", "results": [bar("GCQ5", ns(2025, 6, 1, 22), 3300.0, d1)]}]}
    with pytest.raises(ValueError, match="pagination is incomplete"):
        assemble_evidence_dataset(calendar, pages_by_contract=pages)


def test_evidence_assembly_rejects_extra_or_missing_contract_payloads():
    d1, d2, snapshots, prior_dates, responses = two_day_inputs()
    requests = build_liquidity_request_plan(snapshots, dates=[d1, d2], prior_session_date_by_as_of=prior_dates)
    calendar = build_calendar_from_liquidity_responses(snapshots, requests=requests, responses_by_as_of=responses)
    with pytest.raises(ValueError, match="coverage mismatch"):
        assemble_evidence_dataset(calendar, pages_by_contract={"GCM5": []})


def test_evidence_assembly_marks_first_bar_after_roll_only_when_legacy_buffer_explicitly_requested():
    d1, d2, snapshots, prior_dates, responses = two_day_inputs()
    responses[d1]["GCM5"][0]["volume"] = 200000
    responses[d1]["GCQ5"][0]["volume"] = 100000
    requests = build_liquidity_request_plan(snapshots, dates=[d1, d2], prior_session_date_by_as_of=prior_dates)
    calendar = build_calendar_from_liquidity_responses(snapshots, requests=requests, responses_by_as_of=responses)
    pages = {
        "GCM5": [{"results": [bar("GCM5", ns(2025, 6, 1, 22), 3280.0, d1)]}],
        "GCQ5": [{"results": [bar("GCQ5", ns(2025, 6, 2, 22), 3310.0, d2)]}],
    }
    result = assemble_evidence_dataset(calendar, pages_by_contract=pages, roll_buffer_bars=1)
    assert result.bars[0].is_roll_window is False
    assert result.bars[1].is_roll_window is True
    assert result.manifest.contracts == ("GCM5", "GCQ5")


def test_v5_default_uses_zero_additional_roll_blackout():
    d1, d2, snapshots, prior_dates, responses = two_day_inputs()
    responses[d1]["GCM5"][0]["volume"] = 200000
    responses[d1]["GCQ5"][0]["volume"] = 100000
    requests = build_liquidity_request_plan(snapshots, dates=[d1, d2], prior_session_date_by_as_of=prior_dates)
    calendar = build_calendar_from_liquidity_responses(snapshots, requests=requests, responses_by_as_of=responses)
    pages = {
        "GCM5": [{"results": [bar("GCM5", ns(2025, 6, 1, 22), 3280.0, d1)]}],
        "GCQ5": [{"results": [bar("GCQ5", ns(2025, 6, 2, 22), 3310.0, d2)]}],
    }
    result = assemble_evidence_dataset(calendar, pages_by_contract=pages)
    assert all(not b.is_roll_window for b in result.bars)
