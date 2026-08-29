from datetime import date

import pytest

from gold_cio_v9.data.contract_master import build_gc_contract_master, eligible_master_contracts


def row(ticker, first, last, settlement, *, active=True):
    return {"ticker": ticker, "product_code": "GC", "first_trade_date": first, "last_trade_date": last, "settlement_date": settlement, "active": active}


def test_master_ignores_unreliable_historical_active_flag():
    master = build_gc_contract_master([
        row("GCM6", "2020-06-30", "2026-06-26", "2026-06-26", active=False),
        row("GCU6", "2025-02-10", "2026-09-28", "2026-09-28", active=True),
    ])
    eligible = eligible_master_contracts(master, as_of=date(2026, 3, 27))
    assert [s.ticker for s in eligible] == ["GCM6", "GCU6"]


def test_master_deduplicates_identical_specs_across_snapshots():
    r = row("GCQ6", "2024-09-30", "2026-08-27", "2026-08-27")
    master = build_gc_contract_master([r, dict(r, active=False)])
    assert len(master.specs) == 1


def test_inconsistent_contract_specs_fail_closed():
    with pytest.raises(ValueError, match="inconsistent immutable"):
        build_gc_contract_master([
            row("GCQ6", "2024-09-30", "2026-08-27", "2026-08-27"),
            row("GCQ6", "2024-09-30", "2026-08-28", "2026-08-27"),
        ])


def test_one_year_forward_bound_and_expiry_buffer_are_enforced():
    master = build_gc_contract_master([
        row("GCM6", "2020-06-30", "2026-06-26", "2026-06-26"),
        row("GCQ7", "2025-09-30", "2027-08-27", "2027-08-27"),
    ])
    assert [s.ticker for s in eligible_master_contracts(master, as_of=date(2026, 3, 27))] == ["GCM6"]
    with pytest.raises(ValueError, match="no eligible"):
        eligible_master_contracts(master, as_of=date(2026, 6, 22), roll_buffer_days=5, max_settlement_days_forward=30)


def test_master_hash_changes_when_contract_spec_changes():
    a = build_gc_contract_master([row("GCM6", "2020-06-30", "2026-06-26", "2026-06-26")])
    b = build_gc_contract_master([row("GCM6", "2020-06-29", "2026-06-26", "2026-06-26")])
    assert a.master_hash != b.master_hash
