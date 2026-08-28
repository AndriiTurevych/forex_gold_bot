from datetime import date

import pytest

from gold_cio_v9.data.front_calendar import build_front_contract_calendar


def _row(ticker, as_of, first, last, settle, *, active=True, product="GC"):
    return {
        "ticker": ticker,
        "date": as_of.isoformat(),
        "product_code": product,
        "active": active,
        "first_trade_date": first.isoformat(),
        "last_trade_date": last.isoformat(),
        "settlement_date": settle.isoformat(),
    }


def _snapshot(as_of):
    return [
        _row("GCM5", as_of, date(2019, 6, 28), date(2025, 6, 26), date(2025, 6, 26)),
        _row("GCN5", as_of, date(2025, 2, 10), date(2025, 7, 29), date(2025, 7, 29)),
        _row("GCM5-GCN5", as_of, date(2025, 2, 10), date(2025, 6, 26), date(2025, 6, 26)),
    ]


def test_calendar_selects_front_and_rolls_inside_expiry_buffer():
    d1 = date(2025, 6, 20)  # 6 calendar days before GCM5 last trade -> still front
    d2 = date(2025, 6, 22)  # inside locked 5-day buffer -> roll to GCN5
    cal = build_front_contract_calendar(
        {d1: _snapshot(d1), d2: _snapshot(d2)},
        dates=[d1, d2],
        roll_buffer_days=5,
    )
    assert [x.contract for x in cal.days] == ["GCM5", "GCN5"]
    assert cal.contract_order == ("GCM5", "GCN5")


def test_missing_snapshot_fails_closed():
    d = date(2025, 6, 20)
    with pytest.raises(ValueError, match="missing PIT contract snapshot"):
        build_front_contract_calendar({}, dates=[d])


def test_dates_must_be_strictly_increasing_and_unique():
    d1 = date(2025, 6, 20)
    d2 = date(2025, 6, 19)
    with pytest.raises(ValueError, match="strictly increasing"):
        build_front_contract_calendar({d1: _snapshot(d1), d2: _snapshot(d2)}, dates=[d1, d2])
    with pytest.raises(ValueError, match="duplicates"):
        build_front_contract_calendar({d1: _snapshot(d1)}, dates=[d1, d1])


def test_no_eligible_front_fails_closed():
    d = date(2025, 6, 26)
    rows = [_row("GCM5", d, date(2019, 6, 28), d, d)]
    with pytest.raises(ValueError, match="no eligible front"):
        build_front_contract_calendar({d: rows}, dates=[d], roll_buffer_days=5)


def test_pit_date_mismatch_propagates_fail_closed():
    d = date(2025, 6, 20)
    bad = _snapshot(date(2025, 6, 19))
    with pytest.raises(ValueError, match="date mismatch"):
        build_front_contract_calendar({d: bad}, dates=[d])
