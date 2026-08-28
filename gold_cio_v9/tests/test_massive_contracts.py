from datetime import date

import pytest

from gold_cio_v9.data.massive_contracts import parse_massive_gc_contracts, select_massive_gc_front


AS_OF = date(2025, 6, 2)


def _row(ticker, last, *, first="2024-01-01", settlement=None, active=True, product="GC", row_date="2025-06-02"):
    return {
        "ticker": ticker,
        "product_code": product,
        "active": active,
        "date": row_date,
        "first_trade_date": first,
        "last_trade_date": last,
        "settlement_date": settlement or last,
    }


def test_parser_filters_combo_symbols_even_when_metadata_calls_them_single():
    rows = [
        _row("GCM5", "2025-06-26"),
        _row("GCM5-GCQ5", "2025-06-26"),
        _row("GCQ5", "2025-08-27"),
    ]
    specs = parse_massive_gc_contracts(rows, as_of=AS_OF)
    assert [s.ticker for s in specs] == ["GCM5", "GCQ5"]


def test_front_selection_is_maturity_based_without_volume_or_oi():
    rows = [_row("GCM5", "2025-06-26"), _row("GCQ5", "2025-08-27")]
    assert select_massive_gc_front(rows, as_of=AS_OF, roll_buffer_days=5) == "GCM5"


def test_front_selection_skips_contract_inside_expiry_buffer():
    as_of = date(2025, 6, 23)
    rows = [
        _row("GCM5", "2025-06-26", row_date="2025-06-23"),
        _row("GCQ5", "2025-08-27", row_date="2025-06-23"),
    ]
    assert select_massive_gc_front(rows, as_of=as_of, roll_buffer_days=5) == "GCQ5"


def test_pit_date_mismatch_fails_closed():
    with pytest.raises(ValueError, match="date mismatch"):
        parse_massive_gc_contracts([_row("GCM5", "2025-06-26", row_date="2025-06-01")], as_of=AS_OF)


def test_duplicate_outright_metadata_fails_closed():
    row = _row("GCM5", "2025-06-26")
    with pytest.raises(ValueError, match="duplicate"):
        parse_massive_gc_contracts([row, dict(row)], as_of=AS_OF)


def test_non_gc_inactive_and_invalid_symbols_do_not_enter_chain():
    rows = [
        _row("SIU5", "2025-09-26", product="SI"),
        _row("GCU5", "2025-09-26", active=False),
        _row("GC_BAD", "2025-09-26"),
        _row("GCZ5", "2025-12-29"),
    ]
    specs = parse_massive_gc_contracts(rows, as_of=AS_OF)
    assert [s.ticker for s in specs] == ["GCZ5"]


def test_no_outrights_fails_closed():
    with pytest.raises(ValueError, match="no active outright"):
        parse_massive_gc_contracts([_row("GCM5-GCQ5", "2025-06-26")], as_of=AS_OF)
