from datetime import date

import pytest

from gold_cio_v9.data.contract_chain import ContractSpec, eligible_contracts, is_roll_buffer, select_front_contract


def _spec(ticker, first, last):
    return ContractSpec(ticker, date.fromisoformat(first), date.fromisoformat(last), date.fromisoformat(last))


def test_nearest_active_contract_selected_outside_buffer():
    specs = [_spec("GCZ5", "2024-01-01", "2025-12-29"), _spec("GCG6", "2024-06-01", "2026-02-25")]
    assert select_front_contract(specs, date(2025, 12, 1), roll_buffer_days=5) == "GCZ5"


def test_roll_buffer_skips_expiring_contract_without_price_adjustment():
    specs = [_spec("GCZ5", "2024-01-01", "2025-12-29"), _spec("GCG6", "2024-06-01", "2026-02-25")]
    assert is_roll_buffer(specs[0], date(2025, 12, 27), roll_buffer_days=5)
    assert select_front_contract(specs, date(2025, 12, 27), roll_buffer_days=5) == "GCG6"


def test_no_eligible_contract_fails_closed():
    specs = [_spec("GCZ5", "2024-01-01", "2025-12-29")]
    assert select_front_contract(specs, date(2026, 1, 2)) is None


def test_spread_contract_rejected():
    with pytest.raises(ValueError):
        _spec("GCZ5-GCG6", "2024-01-01", "2025-12-29")


def test_active_contract_order_is_deterministic():
    specs = [_spec("GCG6", "2024-06-01", "2026-02-25"), _spec("GCZ5", "2024-01-01", "2025-12-29")]
    assert [x.ticker for x in eligible_contracts(specs, date(2025, 12, 1))] == ["GCZ5", "GCG6"]
