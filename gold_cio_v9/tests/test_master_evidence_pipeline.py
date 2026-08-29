from datetime import date, datetime, timezone

import pytest

from gold_cio_v9.data.contract_master import build_gc_contract_master
from gold_cio_v9.data.master_evidence_pipeline import build_master_evidence_dataset


def meta(ticker, first, last, settlement, *, active=True):
    return {
        "ticker": ticker, "product_code": "GC", "active": active,
        "first_trade_date": first, "last_trade_date": last, "settlement_date": settlement,
    }


def srow(ticker, session_date, volume):
    return {"ticker": ticker, "session_end_date": session_date.isoformat(), "volume": volume}


def bar(ticker, d, minute, px):
    ts = int(datetime(d.year, d.month, d.day, 12, minute, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    return {"ticker": ticker, "window_start": ts, "open": px, "high": px + 1, "low": px - 1, "close": px + .5, "volume": 10}


def fixture():
    master = build_gc_contract_master([
        meta("GCM6", "2020-06-30", "2026-06-26", "2026-06-26", active=False),
        meta("GCU6", "2025-02-10", "2026-09-28", "2026-09-28", active=True),
    ])
    d1, d2 = date(2026, 3, 27), date(2026, 3, 30)
    p1, p2 = date(2026, 3, 26), date(2026, 3, 27)
    prior = {d1: p1, d2: p2}
    responses = {
        d1: {"GCM6": [srow("GCM6", p1, 60169)], "GCU6": [srow("GCU6", p1, 3)]},
        d2: {"GCM6": [srow("GCM6", p2, 80000)], "GCU6": [srow("GCU6", p2, 5)]},
    }
    pages = {"GCM6": [{"results": [bar("GCM6", d1, 0, 4500), bar("GCM6", d2, 0, 4510)]}]}
    return master, (d1, d2), prior, responses, pages


def test_master_pipeline_selects_trading_contract_missing_from_provider_active_flag():
    master, dates, prior, responses, pages = fixture()
    out = build_master_evidence_dataset(
        master=master, dates=dates, prior_session_date_by_as_of=prior,
        liquidity_responses_by_as_of=responses, pages_by_contract=pages,
    )
    assert out.dataset.calendar.contract_order == ("GCM6",)
    assert tuple(d.contract for d in out.dataset.calendar.days) == ("GCM6", "GCM6")
    assert out.lineage.contract_master_hash == master.master_hash
    assert out.lineage.dataset_hash == out.dataset.manifest.dataset_hash
    assert out.lineage.max_settlement_days_forward == 365


def test_missing_competitor_response_fails_closed_before_dataset_assembly():
    master, dates, prior, responses, pages = fixture()
    bad = {d: dict(v) for d, v in responses.items()}
    del bad[dates[0]]["GCU6"]
    with pytest.raises(ValueError, match="missing"):
        build_master_evidence_dataset(
            master=master, dates=dates, prior_session_date_by_as_of=prior,
            liquidity_responses_by_as_of=bad, pages_by_contract=pages,
        )


def test_incomplete_or_wrong_contract_pages_fail_closed():
    master, dates, prior, responses, _ = fixture()
    with pytest.raises(ValueError, match="coverage mismatch"):
        build_master_evidence_dataset(
            master=master, dates=dates, prior_session_date_by_as_of=prior,
            liquidity_responses_by_as_of=responses, pages_by_contract={"GCU6": []},
        )


def test_contract_master_change_changes_lineage_identity():
    master, dates, prior, responses, pages = fixture()
    a = build_master_evidence_dataset(
        master=master, dates=dates, prior_session_date_by_as_of=prior,
        liquidity_responses_by_as_of=responses, pages_by_contract=pages,
    )
    changed_master = build_gc_contract_master([
        meta("GCM6", "2020-06-29", "2026-06-26", "2026-06-26", active=False),
        meta("GCU6", "2025-02-10", "2026-09-28", "2026-09-28", active=True),
    ])
    b = build_master_evidence_dataset(
        master=changed_master, dates=dates, prior_session_date_by_as_of=prior,
        liquidity_responses_by_as_of=responses, pages_by_contract=pages,
    )
    assert a.dataset.manifest.dataset_hash == b.dataset.manifest.dataset_hash
    assert a.lineage.contract_master_hash != b.lineage.contract_master_hash
    assert a.lineage.lineage_hash != b.lineage.lineage_hash
