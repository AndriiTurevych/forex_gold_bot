from datetime import date, datetime, timedelta, timezone

import pytest

import gold_cio_v9.validation.exp0001_full_test as formal
from gold_cio_v9.backtest.costs import CostAssumptions
from gold_cio_v9.data.dataset_manifest import build_gc_dataset_manifest
from gold_cio_v9.data.evidence_lineage import AcquisitionLineageManifest
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.experiments.exp0001_locked import LOCKED_BASE_COSTS
from gold_cio_v9.validation.acceptance import ValidationMetrics
from gold_cio_v9.validation.exp0001_full_validation import ChronologicalPartition, FullValidationBuild, FullValidationDiagnostics
from gold_cio_v9.validation.ledger import EvidenceLedger
from gold_cio_v9.validation.macro_calendar import build_macro_calendar_snapshot
from gold_cio_v9.validation.trials import TrialsRegistry


def _bars():
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return tuple(HistoricalBar(
        instrument="GC", contract="GCG5", event_time=t0 + timedelta(minutes=i),
        open=100.0, high=101.0, low=99.0, close=100.0, volume=10.0,
        quality_state=QualityState.VERIFIED, source_id="TEST", roll_method=RollMethod.RAW_CONTRACT,
    ) for i in range(3))


def _lineage(dataset_hash, *, master_hash="master-hash"):
    return AcquisitionLineageManifest(5, 0, (), (), dataset_hash, "lineage", 365, master_hash)


def _macro(start=date(2025, 1, 1), end=date(2025, 1, 2)):
    return build_macro_calendar_snapshot(coverage_start=start, coverage_end=end, source_id="calendar:test", events=())


def _validation():
    metrics = ValidationMetrics(
        oos_expectancy=1.0, oos_profit_factor=2.0, raw_oos_setups=250,
        effective_sample_ok=True, walk_forward_stable=True, holdout_expectancy=1.0,
        dsr_ok=True, pbo=0.0, expectancy_cost_1_5x=0.5,
        top_trade_removal_ok=True, concentration_ok=True, catastrophic_regime=False,
        data_integrity_ok=True, post_result_parameter_edits=False,
        ambiguous_oos_setups=0, ambiguity_rate=0.0,
    )
    diagnostics = FullValidationDiagnostics(
        total_primary_candidates=1000, resolved_oos=250, ambiguous_oos=0,
        resolved_holdout=250, walk_forward_test_expectancies=(1.0,), pbo=0.0,
        dsr_p_value=0.001, top_positive_pnl_share=0.2,
        expectancy_after_top_removal=0.5, catastrophic_regimes=(), low_n_negative_regimes=(),
    )
    return FullValidationBuild(ChronologicalPartition(("d",), ("o",), ("h",)), metrics, diagnostics)


def test_formal_orchestrator_registers_before_results_and_ledgers_before_return(tmp_path, monkeypatch):
    bars = _bars()
    manifest = build_gc_dataset_manifest(bars)
    lineage = _lineage(manifest.dataset_hash)
    registry = TrialsRegistry(tmp_path / "trials.jsonl")
    ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
    calls = []

    def fake_book(*, bars, costs):
        assert len(registry.read_all()) == 1
        calls.append(costs.stress_multiple)
        return object()

    monkeypatch.setattr(formal, "build_exp0001_evidence_book", fake_book)
    monkeypatch.setattr(formal, "build_regime_labels", lambda **kwargs: {})
    monkeypatch.setattr(formal, "build_validation_metrics", lambda **kwargs: _validation())
    monkeypatch.setattr(formal, "_candidate_hash", lambda book: "candidates")
    monkeypatch.setattr(formal, "_book_result_payload", lambda book: [])

    out = formal.run_formal_exp0001_test(
        bars=bars, dataset_manifest=manifest, acquisition_lineage=lineage,
        macro_calendar=_macro(), base_costs=LOCKED_BASE_COSTS,
        trial_registry=registry, evidence_ledger=ledger, git_commit="abc123",
    )
    assert calls == [1.0, 1.5]
    assert out.verdict == "ACCEPT"
    assert out.trial.config_hash
    rows = ledger.read_all()
    assert len(rows) == 1
    assert rows[0]["verdict"] == "ACCEPT"
    assert rows[0]["candidate_snapshot_hash"] == "candidates"


def test_manifest_mismatch_fails_before_trial_registration(tmp_path):
    bars = _bars()
    manifest = build_gc_dataset_manifest(bars)
    bad = type(manifest)(manifest.instrument, manifest.rows, manifest.contracts, manifest.coverage, "bad")
    registry = TrialsRegistry(tmp_path / "trials.jsonl")
    with pytest.raises(ValueError, match="manifest does not match"):
        formal.run_formal_exp0001_test(
            bars=bars, dataset_manifest=bad, acquisition_lineage=_lineage("bad"),
            macro_calendar=_macro(), base_costs=LOCKED_BASE_COSTS,
            trial_registry=registry, evidence_ledger=EvidenceLedger(tmp_path / "ledger.jsonl"), git_commit="abc",
        )
    assert registry.read_all() == []


def test_missing_contract_master_fails_before_trial_registration(tmp_path):
    bars = _bars()
    manifest = build_gc_dataset_manifest(bars)
    registry = TrialsRegistry(tmp_path / "trials.jsonl")
    with pytest.raises(ValueError, match="immutable contract master"):
        formal.run_formal_exp0001_test(
            bars=bars, dataset_manifest=manifest, acquisition_lineage=_lineage(manifest.dataset_hash, master_hash=""),
            macro_calendar=_macro(), base_costs=LOCKED_BASE_COSTS,
            trial_registry=registry, evidence_ledger=EvidenceLedger(tmp_path / "ledger.jsonl"), git_commit="abc",
        )
    assert registry.read_all() == []


def test_macro_coverage_mismatch_fails_before_trial_registration(tmp_path):
    bars = _bars()
    manifest = build_gc_dataset_manifest(bars)
    registry = TrialsRegistry(tmp_path / "trials.jsonl")
    bad_macro = _macro(start=date(2024, 12, 1), end=date(2024, 12, 31))
    with pytest.raises(ValueError, match="does not cover"):
        formal.run_formal_exp0001_test(
            bars=bars, dataset_manifest=manifest, acquisition_lineage=_lineage(manifest.dataset_hash),
            macro_calendar=bad_macro, base_costs=LOCKED_BASE_COSTS,
            trial_registry=registry, evidence_ledger=EvidenceLedger(tmp_path / "ledger.jsonl"), git_commit="abc",
        )
    assert registry.read_all() == []


def test_any_cost_override_fails_closed_before_trial_registration(tmp_path):
    bars = _bars()
    manifest = build_gc_dataset_manifest(bars)
    registry = TrialsRegistry(tmp_path / "trials.jsonl")
    with pytest.raises(ValueError, match="diverge from locked baseline V5"):
        formal.run_formal_exp0001_test(
            bars=bars, dataset_manifest=manifest, acquisition_lineage=_lineage(manifest.dataset_hash),
            macro_calendar=_macro(), base_costs=CostAssumptions(0.1, 0.05, 0.05, 1.0),
            trial_registry=registry,
            evidence_ledger=EvidenceLedger(tmp_path / "ledger.jsonl"), git_commit="abc",
        )
    assert registry.read_all() == []
