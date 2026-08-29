from datetime import datetime, timedelta, timezone
import json

import pytest

from gold_cio_v9.backtest.costs import CostAssumptions
from gold_cio_v9.data.dataset_manifest import build_gc_dataset_manifest
from gold_cio_v9.data.evidence_lineage import AcquisitionLineageManifest, RollDecisionLineage
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.validation.evidence_bundle import build_evidence_bundle, dump_evidence_bundle, load_evidence_bundle
from gold_cio_v9.validation.macro_calendar import build_macro_calendar_snapshot


def _bars():
    t0 = datetime(2025, 6, 2, 12, tzinfo=timezone.utc)
    return tuple(HistoricalBar(
        instrument="GC", contract="GCQ5", event_time=t0 + timedelta(minutes=i),
        open=3300+i, high=3302+i, low=3299+i, close=3301+i, volume=10+i,
        quality_state=QualityState.VERIFIED, source_id="massive:test",
        roll_method=RollMethod.RAW_CONTRACT,
    ) for i in range(3))


def _lineage(bars):
    m = build_gc_dataset_manifest(bars)
    return AcquisitionLineageManifest(
        5, 1,
        (RollDecisionLineage("2025-06-02", "2025-05-30", "GCQ5", (("GCM5", 1240.0), ("GCQ5", 179229.0))),),
        (("GCQ5", "2025-06-02", "2025-06-02"),),
        m.dataset_hash, "lineage-locked-hash",
    )


def _macro():
    return build_macro_calendar_snapshot(
        coverage_start=datetime(2025, 6, 1).date(), coverage_end=datetime(2025, 6, 3).date(),
        source_id="calendar:test-snapshot", events=(),
    )


def _costs():
    return CostAssumptions(0.1, 0.05, 0.05, 1.0)


def test_bundle_round_trip_is_deterministic(tmp_path):
    bars = _bars()
    bundle = build_evidence_bundle(bars=bars, acquisition_lineage=_lineage(bars), macro_calendar=_macro(), base_costs=_costs())
    p = tmp_path / "evidence.json"
    dump_evidence_bundle(bundle, p)
    loaded = load_evidence_bundle(p)
    assert loaded.bundle_hash == bundle.bundle_hash
    assert loaded.dataset_hash == bundle.dataset_hash
    assert loaded.bars == bars
    assert loaded.macro_calendar.calendar_hash == _macro().calendar_hash
    assert loaded.base_costs == _costs()


def test_price_tamper_is_rejected(tmp_path):
    bars = _bars()
    bundle = build_evidence_bundle(bars=bars, acquisition_lineage=_lineage(bars), macro_calendar=_macro(), base_costs=_costs())
    p = tmp_path / "evidence.json"
    dump_evidence_bundle(bundle, p)
    raw = json.loads(p.read_text())
    raw["payload"]["bars"][0]["close"] = 3301.5
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="bundle hash mismatch"):
        load_evidence_bundle(p)


def test_macro_calendar_hash_tamper_is_rejected(tmp_path):
    bars = _bars()
    bundle = build_evidence_bundle(bars=bars, acquisition_lineage=_lineage(bars), macro_calendar=_macro(), base_costs=_costs())
    p = tmp_path / "evidence.json"
    dump_evidence_bundle(bundle, p)
    raw = json.loads(p.read_text())
    raw["payload"]["macro_calendar"]["calendar_hash"] = "wrong"
    # Recompute only the outer hash to prove the inner macro identity is independently checked.
    from hashlib import sha256
    payload = raw["payload"]
    raw["bundle_hash"] = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="macro calendar hash mismatch"):
        load_evidence_bundle(p)


def test_lineage_dataset_mismatch_fails_before_bundle_creation():
    bars = _bars()
    bad = AcquisitionLineageManifest(5, 1, _lineage(bars).decisions, _lineage(bars).fetch_windows, "wrong", "lineage")
    with pytest.raises(ValueError, match="lineage does not bind"):
        build_evidence_bundle(bars=bars, acquisition_lineage=bad, macro_calendar=_macro(), base_costs=_costs())


def test_macro_coverage_gap_is_rejected_before_bundle_creation():
    bars = _bars()
    incomplete = build_macro_calendar_snapshot(
        coverage_start=datetime(2025, 6, 1).date(), coverage_end=datetime(2025, 6, 1).date(),
        source_id="calendar:incomplete", events=(),
    )
    with pytest.raises(ValueError, match="does not cover"):
        build_evidence_bundle(bars=bars, acquisition_lineage=_lineage(bars), macro_calendar=incomplete, base_costs=_costs())


def test_non_base_stress_costs_are_rejected():
    bars = _bars()
    with pytest.raises(ValueError, match="stress_multiple=1.0"):
        build_evidence_bundle(
            bars=bars, acquisition_lineage=_lineage(bars), macro_calendar=_macro(),
            base_costs=CostAssumptions(0.1, 0.05, 0.05, 1.5),
        )
