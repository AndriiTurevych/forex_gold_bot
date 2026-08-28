from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.data.dataset_assembly import assemble_gc_dataset
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod


def _bar(contract, minute, *, quality=QualityState.VERIFIED, roll=RollMethod.RAW_CONTRACT):
    t = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minute)
    return HistoricalBar(
        instrument="GC", contract=contract, event_time=t,
        open=100.0, high=101.0, low=99.0, close=100.5, volume=10.0,
        quality_state=quality, source_id="TEST", roll_method=roll,
    )


def test_assembly_preserves_raw_prices_and_marks_contract_boundary():
    data = assemble_gc_dataset(
        {"GCG6": [_bar("GCG6", 1), _bar("GCG6", 2)],
         "GCJ6": [_bar("GCJ6", 10), _bar("GCJ6", 11)]},
        contract_order=["GCG6", "GCJ6"], roll_buffer_bars=1,
    )
    assert [b.contract for b in data] == ["GCG6", "GCG6", "GCJ6", "GCJ6"]
    assert [b.close for b in data] == [100.5] * 4
    assert [b.is_roll_window for b in data] == [False, False, True, False]


def test_missing_contract_fails_closed():
    with pytest.raises(ValueError, match="missing bars"):
        assemble_gc_dataset({"GCG6": [_bar("GCG6", 1)]}, contract_order=["GCG6", "GCJ6"])


def test_duplicate_contract_order_fails_closed():
    with pytest.raises(ValueError, match="duplicates"):
        assemble_gc_dataset({"GCG6": [_bar("GCG6", 1)]}, contract_order=["GCG6", "GCG6"])


def test_overlapping_contract_windows_fail_closed():
    with pytest.raises(ValueError, match="overlap"):
        assemble_gc_dataset(
            {"GCG6": [_bar("GCG6", 10)], "GCJ6": [_bar("GCJ6", 9)]},
            contract_order=["GCG6", "GCJ6"],
        )


def test_adjusted_or_bad_quality_data_fail_closed():
    with pytest.raises(ValueError, match="adjusted"):
        assemble_gc_dataset(
            {"GCG6": [_bar("GCG6", 1, roll=RollMethod.DIFFERENCE_ADJUSTED)]},
            contract_order=["GCG6"],
        )
    with pytest.raises(ValueError, match="non-authoritative"):
        assemble_gc_dataset(
            {"GCG6": [_bar("GCG6", 1, quality=QualityState.BAD)]},
            contract_order=["GCG6"],
        )


def test_contract_identity_mismatch_fails_closed():
    with pytest.raises(ValueError, match="identity mismatch"):
        assemble_gc_dataset({"GCG6": [_bar("GCJ6", 1)]}, contract_order=["GCG6"])
