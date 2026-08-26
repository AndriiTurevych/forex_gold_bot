from datetime import datetime, timezone

import pytest

from gold_cio_v9.data.governance import (
    HistoricalBar,
    QualityState,
    RollMethod,
    eligible_for_signal_generation,
    require_dataset_ready,
)

UTC = timezone.utc
T0 = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)


def gc_bar(**kwargs):
    base = dict(
        instrument="GC",
        contract="GCG26",
        event_time=T0,
        open=4500.0,
        high=4502.0,
        low=4498.0,
        close=4501.0,
        volume=100.0,
        quality_state=QualityState.VERIFIED,
        source_id="primary-vendor",
        roll_method=RollMethod.RAW_CONTRACT,
        is_roll_window=False,
    )
    base.update(kwargs)
    return HistoricalBar(**base)


def test_gc_requires_explicit_contract_identity():
    with pytest.raises(ValueError, match="contract identity"):
        gc_bar(contract=None)


def test_adjusted_continuous_gc_not_authoritative_for_signal_generation():
    bar = gc_bar(roll_method=RollMethod.DIFFERENCE_ADJUSTED)
    assert eligible_for_signal_generation(bar) is False
    with pytest.raises(ValueError, match="raw contract-level"):
        require_dataset_ready([bar], instrument="GC")


def test_stale_proxy_bad_data_fail_closed():
    for state in (QualityState.STALE, QualityState.PROXY, QualityState.BAD):
        bar = gc_bar(quality_state=state)
        assert eligible_for_signal_generation(bar) is False
        with pytest.raises(ValueError, match="quality_state"):
            require_dataset_ready([bar], instrument="GC")


def test_roll_window_excluded_from_evidence_dataset():
    bar = gc_bar(is_roll_window=True)
    assert eligible_for_signal_generation(bar) is False
    with pytest.raises(ValueError, match="roll-window"):
        require_dataset_ready([bar], instrument="GC")


def test_clean_raw_contract_dataset_is_ready():
    bars = [gc_bar(), gc_bar(event_time=datetime(2026, 1, 5, 14, 31, tzinfo=UTC), close=4500.5)]
    require_dataset_ready(bars, instrument="GC")
    assert all(eligible_for_signal_generation(b) for b in bars)
