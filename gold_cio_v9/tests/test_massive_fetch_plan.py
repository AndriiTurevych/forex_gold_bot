from datetime import date, datetime, timezone

import pytest

from gold_cio_v9.data.front_calendar import FrontContractCalendar, FrontContractDay
from gold_cio_v9.data.massive_fetch_plan import (
    build_contract_fetch_plan,
    parse_complete_massive_gc_pages,
)


def _row(ticker: str, minute: int):
    ts = datetime(2025, 6, 2, 0, minute, tzinfo=timezone.utc)
    return {
        "ticker": ticker,
        "window_start": int(ts.timestamp() * 1_000_000_000),
        "open": 3300.0,
        "high": 3301.0,
        "low": 3299.0,
        "close": 3300.5,
        "volume": 10.0,
    }


def test_calendar_compresses_to_one_window_per_contract():
    cal = FrontContractCalendar(
        days=(
            FrontContractDay(date(2025, 6, 2), "GCM5"),
            FrontContractDay(date(2025, 6, 3), "GCM5"),
            FrontContractDay(date(2025, 6, 4), "GCN5"),
            FrontContractDay(date(2025, 6, 6), "GCN5"),
        ),
        contract_order=("GCM5", "GCN5"),
    )
    plan = build_contract_fetch_plan(cal)
    assert [(p.contract, p.start_date, p.end_date) for p in plan] == [
        ("GCM5", date(2025, 6, 2), date(2025, 6, 3)),
        ("GCN5", date(2025, 6, 4), date(2025, 6, 6)),
    ]


def test_fetch_plan_reentry_fails_closed():
    cal = FrontContractCalendar(
        days=(
            FrontContractDay(date(2025, 6, 2), "GCM5"),
            FrontContractDay(date(2025, 6, 3), "GCN5"),
            FrontContractDay(date(2025, 6, 4), "GCM5"),
        ),
        contract_order=("GCM5", "GCN5"),
    )
    with pytest.raises(ValueError, match="re-enter"):
        build_contract_fetch_plan(cal)


def test_complete_pages_parse_and_preserve_contract():
    pages = [
        {"request_id": "a", "results": [_row("GCM5", 0)], "next_url": "cursor-2"},
        {"request_id": "b", "results": [_row("GCM5", 1)]},
    ]
    bars = parse_complete_massive_gc_pages(
        pages,
        expected_contract="GCM5",
        start_date=date(2025, 6, 2),
        end_date=date(2025, 6, 2),
    )
    assert len(bars) == 2
    assert {b.contract for b in bars} == {"GCM5"}


def test_final_page_with_next_url_is_incomplete():
    pages = [{"request_id": "a", "results": [_row("GCM5", 0)], "next_url": "cursor-2"}]
    with pytest.raises(ValueError, match="incomplete"):
        parse_complete_massive_gc_pages(
            pages,
            expected_contract="GCM5",
            start_date=date(2025, 6, 2),
            end_date=date(2025, 6, 2),
        )


def test_duplicate_across_page_boundary_fails_closed():
    row = _row("GCM5", 0)
    pages = [
        {"request_id": "a", "results": [row], "next_url": "cursor-2"},
        {"request_id": "b", "results": [row]},
    ]
    with pytest.raises(ValueError, match="duplicate aggregate bar"):
        parse_complete_massive_gc_pages(
            pages,
            expected_contract="GCM5",
            start_date=date(2025, 6, 2),
            end_date=date(2025, 6, 2),
        )


def test_unexpected_contract_fails_closed():
    pages = [{"request_id": "a", "results": [_row("GCN5", 0)]}]
    with pytest.raises(ValueError, match="unexpected contract"):
        parse_complete_massive_gc_pages(
            pages,
            expected_contract="GCM5",
            start_date=date(2025, 6, 2),
            end_date=date(2025, 6, 2),
        )
