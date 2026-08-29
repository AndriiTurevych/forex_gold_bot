from datetime import datetime, timedelta, timezone
import json

import pytest

from gold_cio_v9.backtest.costs import CostAssumptions
from gold_cio_v9.data.contract_master import build_gc_contract_master
from gold_cio_v9.data.dataset_manifest import build_gc_dataset_manifest
from gold_cio_v9.data.evidence_lineage import (
    AcquisitionLineageManifest,
    RollDecisionLineage,
    compute_acquisition_lineage_hash,
)
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.experiments.exp0001_locked import LOCKED_BASE_COSTS
from gold_cio_v9.validation.evidence_bundle import build_evidence_bundle, dump_evidence_bundle, load_evidence_bundle
from gold_cio_v9.validation.macro_calendar import build_macro_calendar_snapshot


def _bars():
    t0 = datetime(2025, 6, 2, 12, tzinfo=timezone.utc)
    return tuple(HistoricalBar(
        instrument="GC", contract="GCQ5", event_time=t0 + timedelta(minutes=i),
        open=3300.0+i, high=3302.0+i, low=3299.0+i, close=3301.0+i, volume=10.0+i,
        quality_state=QualityState.VERIFIED, source_id="massive:test",
        roll_method=RollMethod.RAW_CONTRACT,
    ) for i in range(3))


def _master():
    return build_gc_contract_master(({
        "ticker": "GCQ5", "product_code": "GC",
        "first_trade_date": "2023-09-29", "last_trade_date": "2025-08-27",
        "settlement_date": "2025-08-27",
    },))


def _lineage(bars, *, master_hash=None):
    m = build_gc_dataset_manifest(bars)
    mh = _master().master_hash if master_hash is None else master_hash
    provisional = AcquisitionLineageManifest(
        5, 0,
        (RollDecisionLineage("2025-06-02", "2025-05-30", "GCQ5", (("GCQ5", 179229.0),)),),
        (("GCQ5", "2025-06-02", "2025-06-02"),),
        m.dataset_hash, "PENDING", 365, mh,
    )
    return AcquisitionLineageManifest(
        provisional.roll_buffer_days, provisional.roll_buffer_bars,
        provisional.decisions, provisional.fetch_windows, provisional.dataset_hash,
        compute_acquisition_lineage_hash(provisional), provisional.max_settlement_days_forward,
        provisional.contract_master_hash,
    )


def _macro():
    return build_macro_calendar_snapshot(
        coverage_start=datetime(2025, 6, 1).date(), coverage_end=datetime(2025, 6, 3).date(),
        source_id="calendar:test-snapshot", events=(),
    )


def _build(bars):
    return build_evidence_bundle(
        bars=bars, acquisition_lineage=_lineage(bars), contract_master=_master(),
        macro_calendar=_macro(), base_costs=LOCKED_BASE_COSTS,
    )


def test_bundle_round_trip_is_deterministic(tmp_path):
    bars = _bars()
    bundle = _build(bars)
    p = tmp_path / "evidence.json"
    dump_evidence_bundle(bundle, p)
    loaded = load_evidence_bundle(p)
    assert loaded.bundle_hash == bundle.bundle_hash
    assert loaded.dataset_hash == bundle.dataset_hash
    assert loaded.bars == bars
    assert loaded.contract_master.master_hash == _master().master_hash
    assert loaded.acquisition_lineage.contract_master_hash == _master().master_hash
    assert loaded.acquisition_lineage.max_settlement_days_forward == 365
    assert loaded.acquisition_lineage.roll_buffer_bars == 0
    assert loaded.macro_calendar.calendar_hash == _macro().calendar_hash
    assert loaded.base_costs == LOCKED_BASE_COSTS


def test_price_tamper_is_rejected(tmp_path):
    bundle = _build(_bars())
    p = tmp_path / "evidence.json"
    dump_evidence_bundle(bundle, p)
    raw = json.loads(p.read_text())
    raw["payload"]["bars"][0]["close"] = 3301.5
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="bundle hash mismatch"):
        load_evidence_bundle(p)


def test_contract_master_tamper_is_rejected_even_if_outer_hash_is_recomputed(tmp_path):
    bundle = _build(_bars())
    p = tmp_path / "evidence.json"
    dump_evidence_bundle(bundle, p)
    raw = json.loads(p.read_text())
    raw["payload"]["contract_master"]["specs"][0]["settlement_date"] = "2025-08-28"
    from hashlib import sha256
    payload = raw["payload"]
    raw["bundle_hash"] = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="contract master hash mismatch"):
        load_evidence_bundle(p)


def test_lineage_tamper_is_rejected_even_if_outer_hash_is_recomputed(tmp_path):
    bundle = _build(_bars())
    p = tmp_path / "evidence.json"
    dump_evidence_bundle(bundle, p)
    raw = json.loads(p.read_text())
    raw["payload"]["acquisition_lineage"]["decisions"][0]["volume_by_contract"][0][1] = 1.0
    from hashlib import sha256
    payload = raw["payload"]
    raw["bundle_hash"] = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="acquisition lineage hash mismatch"):
        load_evidence_bundle(p)


def test_macro_calendar_hash_tamper_is_rejected(tmp_path):
    bundle = _build(_bars())
    p = tmp_path / "evidence.json"
    dump_evidence_bundle(bundle, p)
    raw = json.loads(p.read_text())
    raw["payload"]["macro_calendar"]["calendar_hash"] = "wrong"
    from hashlib import sha256
    payload = raw["payload"]
    raw["bundle_hash"] = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="macro calendar hash mismatch"):
        load_evidence_bundle(p)


def test_lineage_dataset_mismatch_fails_before_bundle_creation():
    bars = _bars()
    good = _lineage(bars)
    provisional = AcquisitionLineageManifest(5, 0, good.decisions, good.fetch_windows, "wrong", "PENDING", 365, _master().master_hash)
    bad = AcquisitionLineageManifest(5, 0, good.decisions, good.fetch_windows, "wrong", compute_acquisition_lineage_hash(provisional), 365, _master().master_hash)
    with pytest.raises(ValueError, match="lineage does not bind"):
        build_evidence_bundle(bars=bars, acquisition_lineage=bad, contract_master=_master(), macro_calendar=_macro(), base_costs=LOCKED_BASE_COSTS)


def test_contract_master_lineage_mismatch_fails_before_bundle_creation():
    bars = _bars()
    lineage = _lineage(bars, master_hash="different-master-hash")
    with pytest.raises(ValueError, match="contract master does not bind"):
        build_evidence_bundle(bars=bars, acquisition_lineage=lineage, contract_master=_master(), macro_calendar=_macro(), base_costs=LOCKED_BASE_COSTS)


def test_macro_coverage_gap_is_rejected_before_bundle_creation():
    bars = _bars()
    incomplete = build_macro_calendar_snapshot(
        coverage_start=datetime(2025, 6, 1).date(), coverage_end=datetime(2025, 6, 1).date(),
        source_id="calendar:incomplete", events=(),
    )
    with pytest.raises(ValueError, match="does not cover"):
        build_evidence_bundle(bars=bars, acquisition_lineage=_lineage(bars), contract_master=_master(), macro_calendar=incomplete, base_costs=LOCKED_BASE_COSTS)


def test_non_locked_costs_are_rejected():
    bars = _bars()
    with pytest.raises(ValueError, match="diverge from locked baseline V5"):
        build_evidence_bundle(
            bars=bars, acquisition_lineage=_lineage(bars), contract_master=_master(), macro_calendar=_macro(),
            base_costs=CostAssumptions(0.1, 0.05, 0.05, 1.0),
        )
