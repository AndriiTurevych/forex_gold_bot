from datetime import date, datetime, timezone

import pytest

from gold_cio_v9.data.evidence_dataset_pipeline import (
    assemble_evidence_dataset,
    build_calendar_from_liquidity_responses,
    build_liquidity_request_plan,
)
from gold_cio_v9.data.evidence_lineage import build_acquisition_lineage_manifest


def meta(ticker, as_of, settlement):
    return {
        "ticker": ticker,
        "product_code": "GC",
        "active": True,
        "date": as_of.isoformat(),
        "first_trade_date": "2024-01-01",
        "last_trade_date": settlement,
        "settlement_date": settlement,
    }


def srow(ticker, session_date, volume):
    return {"ticker": ticker, "session_end_date": session_date.isoformat(), "volume": volume}


def bar(ticker, d, px):
    ts = int(datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    return {
        "ticker": ticker,
        "session_end_date": d.isoformat(),
        "window_start": ts,
        "open": px,
        "high": px + 1,
        "low": px - 1,
        "close": px + .5,
        "volume": 10,
    }


def fixture():
    d = date(2025, 6, 2)
    s = date(2025, 5, 30)
    snapshots = {d: [meta("GCM5", d, "2025-06-27"), meta("GCQ5", d, "2025-08-27")]}
    prior_dates = {d: s}
    responses = {d: {"GCM5": [srow("GCM5", s, 1240)], "GCQ5": [srow("GCQ5", s, 179229)]}}
    requests = build_liquidity_request_plan(snapshots, dates=[d], prior_session_date_by_as_of=prior_dates)
    calendar = build_calendar_from_liquidity_responses(snapshots, requests=requests, responses_by_as_of=responses)
    dataset = assemble_evidence_dataset(calendar, pages_by_contract={"GCQ5": [{"results": [bar("GCQ5", d, 3300)]}]})
    return requests, responses, calendar, dataset


def test_lineage_hash_is_deterministic_and_contains_competitor_volumes():
    requests, responses, calendar, dataset = fixture()
    a = build_acquisition_lineage_manifest(
        requests=requests,
        responses_by_as_of=responses,
        calendar=calendar,
        fetch_windows=dataset.fetch_windows,
        dataset_manifest=dataset.manifest,
        roll_buffer_days=5,
        roll_buffer_bars=1,
    )
    b = build_acquisition_lineage_manifest(
        requests=requests,
        responses_by_as_of=responses,
        calendar=calendar,
        fetch_windows=dataset.fetch_windows,
        dataset_manifest=dataset.manifest,
        roll_buffer_days=5,
        roll_buffer_bars=1,
    )
    assert a.lineage_hash == b.lineage_hash
    assert a.decisions[0].selected_contract == "GCQ5"
    assert a.decisions[0].volume_by_contract == (("GCM5", 1240.0), ("GCQ5", 179229.0))


def test_lineage_hash_changes_if_roll_evidence_changes_even_when_winner_does_not():
    requests, responses, calendar, dataset = fixture()
    a = build_acquisition_lineage_manifest(
        requests=requests, responses_by_as_of=responses, calendar=calendar,
        fetch_windows=dataset.fetch_windows, dataset_manifest=dataset.manifest,
        roll_buffer_days=5, roll_buffer_bars=1,
    )
    changed = {k: {t: [dict(row) for row in rows] for t, rows in v.items()} for k, v in responses.items()}
    changed[requests[0].as_of]["GCM5"][0]["volume"] = 1300
    b = build_acquisition_lineage_manifest(
        requests=requests, responses_by_as_of=changed, calendar=calendar,
        fetch_windows=dataset.fetch_windows, dataset_manifest=dataset.manifest,
        roll_buffer_days=5, roll_buffer_bars=1,
    )
    assert a.lineage_hash != b.lineage_hash
    assert b.decisions[0].selected_contract == "GCQ5"


def test_lineage_hash_changes_with_dataset_hash_or_policy_parameters():
    requests, responses, calendar, dataset = fixture()
    a = build_acquisition_lineage_manifest(
        requests=requests, responses_by_as_of=responses, calendar=calendar,
        fetch_windows=dataset.fetch_windows, dataset_manifest=dataset.manifest,
        roll_buffer_days=5, roll_buffer_bars=1,
    )
    b = build_acquisition_lineage_manifest(
        requests=requests, responses_by_as_of=responses, calendar=calendar,
        fetch_windows=dataset.fetch_windows, dataset_manifest=dataset.manifest,
        roll_buffer_days=7, roll_buffer_bars=1,
    )
    assert a.lineage_hash != b.lineage_hash


def test_lineage_rejects_unplanned_response_date():
    requests, responses, calendar, dataset = fixture()
    bad = dict(responses)
    bad[date(2025, 6, 3)] = {}
    with pytest.raises(ValueError, match="unexpected liquidity response lineage dates"):
        build_acquisition_lineage_manifest(
            requests=requests, responses_by_as_of=bad, calendar=calendar,
            fetch_windows=dataset.fetch_windows, dataset_manifest=dataset.manifest,
            roll_buffer_days=5, roll_buffer_bars=1,
        )
