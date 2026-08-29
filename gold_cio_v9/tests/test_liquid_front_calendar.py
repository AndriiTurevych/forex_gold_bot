from datetime import date

import pytest

from gold_cio_v9.data.causal_roll import PriorSessionLiquidity
from gold_cio_v9.data.liquid_front_calendar import build_liquid_front_calendar


def _row(ticker, as_of, last_trade, settlement):
    return {
        "ticker": ticker,
        "product_code": "GC",
        "active": True,
        "date": as_of.isoformat(),
        "first_trade_date": "2020-01-01",
        "last_trade_date": last_trade.isoformat(),
        "settlement_date": settlement.isoformat(),
    }


def test_calendar_uses_prior_liquidity_and_emits_contract_order():
    d1 = date(2025, 6, 2)
    d2 = date(2025, 6, 3)
    rows1 = [
        _row("GCM5", d1, date(2025, 6, 26), date(2025, 6, 26)),
        _row("GCQ5", d1, date(2025, 8, 27), date(2025, 8, 27)),
    ]
    rows2 = [
        _row("GCM5", d2, date(2025, 6, 26), date(2025, 6, 26)),
        _row("GCQ5", d2, date(2025, 8, 27), date(2025, 8, 27)),
    ]
    cal = build_liquid_front_calendar(
        {d1: rows1, d2: rows2},
        {
            d1: PriorSessionLiquidity(date(2025, 5, 30), {"GCM5": 198, "GCQ5": 2881}),
            d2: PriorSessionLiquidity(date(2025, 6, 2), {"GCM5": 100, "GCQ5": 3000}),
        },
        dates=[d1, d2],
    )
    assert [d.contract for d in cal.days] == ["GCQ5", "GCQ5"]
    assert cal.contract_order == ("GCQ5",)


def test_missing_liquidity_snapshot_fails_closed():
    d = date(2025, 6, 2)
    rows = [_row("GCQ5", d, date(2025, 8, 27), date(2025, 8, 27))]
    with pytest.raises(ValueError, match="missing prior-session liquidity"):
        build_liquid_front_calendar({d: rows}, {}, dates=[d])


def test_contract_reentry_fails_closed():
    d1, d2, d3 = date(2025, 6, 2), date(2025, 6, 3), date(2025, 6, 4)
    snapshots = {
        d: [
            _row("GCM5", d, date(2025, 6, 26), date(2025, 6, 26)),
            _row("GCQ5", d, date(2025, 8, 27), date(2025, 8, 27)),
        ]
        for d in (d1, d2, d3)
    }
    liquidity = {
        d1: PriorSessionLiquidity(date(2025, 5, 30), {"GCM5": 3000, "GCQ5": 100}),
        d2: PriorSessionLiquidity(date(2025, 6, 2), {"GCM5": 100, "GCQ5": 3000}),
        d3: PriorSessionLiquidity(date(2025, 6, 3), {"GCM5": 3000, "GCQ5": 100}),
    }
    with pytest.raises(ValueError, match="re-enters an older contract"):
        build_liquid_front_calendar(snapshots, liquidity, dates=[d1, d2, d3])


def test_non_monotonic_dates_fail_closed():
    d1, d2 = date(2025, 6, 2), date(2025, 6, 3)
    with pytest.raises(ValueError, match="strictly increasing"):
        build_liquid_front_calendar({}, {}, dates=[d2, d1])
