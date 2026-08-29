from datetime import date, datetime, timedelta, timezone

import pytest

from gold_cio_v9.data.contract_master import build_gc_contract_master
from gold_cio_v9.data.dataset_manifest import build_gc_dataset_manifest
from gold_cio_v9.data.evidence_lineage import (
    AcquisitionLineageManifest,
    RollDecisionLineage,
    compute_acquisition_lineage_hash,
)
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.experiments.exp0001_locked import LOCKED_BASE_COSTS
from gold_cio_v9.validation.evidence_bundle import build_evidence_bundle
from gold_cio_v9.validation.exp0001_regimes import MacroEvent
from gold_cio_v9.validation.macro_calendar import build_macro_calendar_snapshot
from gold_cio_v9.validation.test_readiness import assess_exp0001_test_readiness, require_exp0001_test_ready


def _bars(*, source="massive:gc-authoritative"):
    t0 = datetime(2025, 6, 2, 12, tzinfo=timezone.utc)
    return tuple(HistoricalBar(
        instrument="GC", contract="GCQ5", event_time=t0 + timedelta(minutes=i),
        open=3300.0 + i, high=3301.0 + i, low=3299.0 + i, close=3300.5 + i, volume=100.0 + i,
        quality_state=QualityState.VERIFIED, source_id=source, roll_method=RollMethod.RAW_CONTRACT,
    ) for i in range(5))


def _master():
    return build_gc_contract_master(({
        "ticker": "GCQ5", "product_code": "GC",
        "first_trade_date": "2023-09-29", "last_trade_date": "2025-08-27",
        "settlement_date": "2025-08-27",
    },))


def _lineage(bars):
    m = build_gc_dataset_manifest(bars)
    provisional = AcquisitionLineageManifest(
        5, 0,
        (RollDecisionLineage("2025-06-02", "2025-05-30", "GCQ5", (("GCQ5", 179229.0),)),),
        (("GCQ5", "2025-06-02", "2025-06-02"),),
        m.dataset_hash, "PENDING", 365, _master().master_hash,
    )
    return AcquisitionLineageManifest(
        provisional.roll_buffer_days, provisional.roll_buffer_bars,
        provisional.decisions, provisional.fetch_windows, provisional.dataset_hash,
        compute_acquisition_lineage_hash(provisional), provisional.max_settlement_days_forward,
        provisional.contract_master_hash,
    )


def _macro(*, source="official:macro-calendar", with_event=True):
    events = ()
    if with_event:
        events = (MacroEvent(
            datetime(2025, 6, 2, 12, 30, tzinfo=timezone.utc),
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            "CPI",
        ),)
    return build_macro_calendar_snapshot(
        coverage_start=date(2025, 6, 1), coverage_end=date(2025, 6, 3),
        source_id=source, events=events,
    )


def _bundle(*, bars=None, macro=None):
    bars = _bars() if bars is None else bars
    return build_evidence_bundle(
        bars=bars, acquisition_lineage=_lineage(bars), contract_master=_master(),
        macro_calendar=_macro() if macro is None else macro,
        base_costs=LOCKED_BASE_COSTS,
    )


def test_real_identity_bundle_is_ready_without_running_strategy():
    report = assess_exp0001_test_readiness(_bundle())
    assert report.ready is True
    assert report.failed_checks == ()
    assert report.implementation_policy == "EXP-0001-BASELINE-POLICY-V5"
    assert report.validation_policy == "EXP-0001-VALIDATION-POLICY-V5"
    assert report.contracts == ("GCQ5",)
    assert report.macro_events == 1


def test_synthetic_bar_source_blocks_formal_readiness():
    bars = _bars(source="synthetic:fixture")
    report = assess_exp0001_test_readiness(_bundle(bars=bars))
    assert report.ready is False
    assert any(c.name == "real_bar_sources" and not c.passed for c in report.checks)
    with pytest.raises(ValueError, match="TEST_NOT_READY"):
        require_exp0001_test_ready(_bundle(bars=bars))


def test_empty_macro_event_set_blocks_readiness_even_with_coverage():
    report = assess_exp0001_test_readiness(_bundle(macro=_macro(with_event=False)))
    assert report.ready is False
    assert any(c.name == "macro_events_present" and not c.passed for c in report.checks)


def test_test_macro_source_blocks_readiness():
    report = assess_exp0001_test_readiness(_bundle(macro=_macro(source="calendar:test")))
    assert report.ready is False
    assert any(c.name == "macro_source_real" and not c.passed for c in report.checks)
