from datetime import date

import pytest

from gold_cio_v9.data.contract_master import build_gc_contract_master
from gold_cio_v9.data.master_front_calendar import build_master_liquidity_request_plan, build_master_liquid_front_calendar


def row(ticker, first, last, settlement, *, active=True):
    return {"ticker": ticker, "product_code": "GC", "first_trade_date": first, "last_trade_date": last, "settlement_date": settlement, "active": active}


def srow(ticker, session_date, volume):
    return {"ticker": ticker, "session_end_date": session_date.isoformat(), "volume": volume}


def master():
    return build_gc_contract_master([
        row("GCM6", "2020-06-30", "2026-06-26", "2026-06-26", active=False),
        row("GCU6", "2025-02-10", "2026-09-28", "2026-09-28", active=True),
    ])


def test_request_universe_comes_from_master_not_active_flag():
    m = master()
    d = date(2026, 3, 27)
    req = build_master_liquidity_request_plan(m, dates=[d], prior_session_date_by_as_of={d: date(2026, 3, 26)})
    assert req[0].contracts == ("GCM6", "GCU6")


def test_realistic_missing_active_contract_can_still_win_by_prior_volume():
    m = master()
    d = date(2026, 3, 27)
    prior = date(2026, 3, 26)
    req = build_master_liquidity_request_plan(m, dates=[d], prior_session_date_by_as_of={d: prior})
    responses = {d: {
        "GCM6": [srow("GCM6", prior, 60169)],
        "GCU6": [srow("GCU6", prior, 3)],
    }}
    cal = build_master_liquid_front_calendar(m, requests=req, responses_by_as_of=responses)
    assert cal.days[0].contract == "GCM6"


def test_missing_explicit_zero_or_volume_fails_closed():
    m = master()
    d = date(2026, 3, 27)
    prior = date(2026, 3, 26)
    req = build_master_liquidity_request_plan(m, dates=[d], prior_session_date_by_as_of={d: prior})
    with pytest.raises(ValueError, match="missing"):
        build_master_liquid_front_calendar(m, requests=req, responses_by_as_of={d: {"GCM6": [srow("GCM6", prior, 1)]}})
