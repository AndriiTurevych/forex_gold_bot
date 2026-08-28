from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.data.dataset_manifest import build_gc_dataset_manifest
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod


def _bar(contract, minute, *, source="MASSIVE", quality=QualityState.VERIFIED, roll=RollMethod.RAW_CONTRACT):
    t = datetime(2025, 10, 1, tzinfo=timezone.utc) + timedelta(minutes=minute)
    return HistoricalBar(
        instrument="GC", contract=contract, event_time=t,
        open=3890.0, high=3891.0, low=3889.5, close=3890.5, volume=100.0,
        quality_state=quality, source_id=source, roll_method=roll,
    )


def test_manifest_is_deterministic_and_records_contract_coverage():
    bars = [_bar("GCZ5", 0), _bar("GCZ5", 1), _bar("GCG6", 10)]
    a = build_gc_dataset_manifest(bars)
    b = build_gc_dataset_manifest(list(bars))
    assert a.dataset_hash == b.dataset_hash
    assert a.rows == 3
    assert a.contracts == ("GCZ5", "GCG6")
    assert [c.rows for c in a.coverage] == [2, 1]
    assert a.coverage[0].source_ids == ("MASSIVE",)


def test_any_authoritative_field_change_changes_hash():
    bars = [_bar("GCZ5", 0), _bar("GCZ5", 1)]
    changed = [bars[0], HistoricalBar(
        instrument="GC", contract="GCZ5", event_time=bars[1].event_time,
        open=3890.0, high=3892.0, low=3889.5, close=3891.5, volume=100.0,
        quality_state=QualityState.VERIFIED, source_id="MASSIVE", roll_method=RollMethod.RAW_CONTRACT,
    )]
    assert build_gc_dataset_manifest(bars).dataset_hash != build_gc_dataset_manifest(changed).dataset_hash


def test_bad_quality_and_adjusted_prices_fail_closed():
    with pytest.raises(ValueError, match="authoritative"):
        build_gc_dataset_manifest([_bar("GCZ5", 0, quality=QualityState.BAD)])
    with pytest.raises(ValueError, match="raw-contract"):
        build_gc_dataset_manifest([_bar("GCZ5", 0, roll=RollMethod.DIFFERENCE_ADJUSTED)])


def test_non_chronological_or_reappearing_contract_fails_closed():
    with pytest.raises(ValueError, match="chronological"):
        build_gc_dataset_manifest([_bar("GCZ5", 1), _bar("GCZ5", 0)])
    with pytest.raises(ValueError, match="reappear"):
        build_gc_dataset_manifest([_bar("GCZ5", 0), _bar("GCG6", 10), _bar("GCZ5", 20)])
