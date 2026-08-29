"""Ledger-first end-to-end orchestrator for the formal EXP-0001 evidence test."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Sequence

from gold_cio_v9.backtest.costs import CostAssumptions, stressed_costs
from gold_cio_v9.data.dataset_manifest import DatasetManifest, build_gc_dataset_manifest
from gold_cio_v9.data.evidence_lineage import AcquisitionLineageManifest
from gold_cio_v9.data.governance import HistoricalBar
from gold_cio_v9.experiments.exp0001_evidence_book import EvidenceBook, build_exp0001_evidence_book
from gold_cio_v9.experiments.exp0001_locked import (
    IMPLEMENTATION_POLICY_ID,
    PRIMARY_HORIZON_MINUTES,
    STRESS_MULTIPLE,
    VALIDATION_POLICY_ID,
    assert_locked_costs,
)
from gold_cio_v9.validation.acceptance import evaluate_exp0001
from gold_cio_v9.validation.evidence_run import classify_verdict
from gold_cio_v9.validation.exp0001_full_validation import FullValidationBuild, build_validation_metrics
from gold_cio_v9.validation.exp0001_regimes import build_regime_labels
from gold_cio_v9.validation.ledger import EvidenceLedger, EvidenceRecord
from gold_cio_v9.validation.macro_calendar import MacroCalendarSnapshot, validate_macro_calendar_for_bars
from gold_cio_v9.validation.trials import TrialRecord, TrialsRegistry

IMPLEMENTATION_POLICY = IMPLEMENTATION_POLICY_ID
VALIDATION_POLICY = VALIDATION_POLICY_ID


@dataclass(frozen=True)
class FormalExpOutcome:
    verdict: str
    failed_gates: tuple[str, ...]
    trial: TrialRecord
    validation: FullValidationBuild
    evidence_record: EvidenceRecord
    data_snapshot_hash: str
    candidate_snapshot_hash: str
    result_hash: str


def _stable_hash(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode()).hexdigest()


def _candidate_hash(book: EvidenceBook) -> str:
    rows = []
    for cell in book.cells:
        for t in cell.trades:
            rows.append({
                "contract": t.contract, "horizon_minutes": t.horizon_minutes,
                "candidate_id": t.candidate_id, "signal_time": t.signal_time.isoformat(),
                "direction": t.direction,
            })
    rows.sort(key=lambda r: (r["horizon_minutes"], r["signal_time"], r["contract"], r["candidate_id"]))
    return _stable_hash(rows)


def _book_result_payload(book: EvidenceBook) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cell in book.cells:
        rows.append({
            "contract": cell.contract, "horizon_minutes": cell.horizon_minutes,
            "status": cell.status, "context_points": cell.context_points,
            "stream_events": cell.stream_events, "replay_setups": cell.replay_setups,
            "data_snapshot_hash": cell.data_snapshot_hash,
            "candidate_snapshot_hash": cell.candidate_snapshot_hash,
            "result_hash": cell.result_hash,
            "trades": [
                {
                    "candidate_id": t.candidate_id, "signal_time": t.signal_time.isoformat(),
                    "direction": t.direction, "first_touch": t.first_touch,
                    "bars_to_first_touch": t.bars_to_first_touch,
                    "net_pnl_price": t.net_pnl_price if t.resolved else None,
                    "resolved": t.resolved,
                }
                for t in cell.trades
            ],
        })
    return rows


def run_formal_exp0001_test(
    *,
    bars: Sequence[HistoricalBar],
    dataset_manifest: DatasetManifest,
    acquisition_lineage: AcquisitionLineageManifest,
    macro_calendar: MacroCalendarSnapshot,
    base_costs: CostAssumptions,
    trial_registry: TrialsRegistry,
    evidence_ledger: EvidenceLedger,
    git_commit: str,
) -> FormalExpOutcome:
    """Execute the locked formal test after every external input is hash-bound."""
    if not git_commit.strip():
        raise ValueError("git_commit is required")
    assert_locked_costs(base_costs)

    materialized = tuple(bars)
    recomputed = build_gc_dataset_manifest(materialized)
    if recomputed.dataset_hash != dataset_manifest.dataset_hash:
        raise ValueError("supplied dataset manifest does not match authoritative bars")
    if acquisition_lineage.dataset_hash != dataset_manifest.dataset_hash:
        raise ValueError("acquisition lineage does not bind to dataset manifest")
    if not acquisition_lineage.contract_master_hash.strip():
        raise ValueError("formal EXP-0001 requires a hash-bound immutable contract master")
    validate_macro_calendar_for_bars(macro_calendar, materialized)

    data_snapshot_hash = _stable_hash({
        "dataset_hash": dataset_manifest.dataset_hash,
        "lineage_hash": acquisition_lineage.lineage_hash,
        "contract_master_hash": acquisition_lineage.contract_master_hash,
        "max_settlement_days_forward": acquisition_lineage.max_settlement_days_forward,
        "macro_calendar_hash": macro_calendar.calendar_hash,
        "macro_source_id": macro_calendar.source_id,
        "macro_coverage_start": macro_calendar.coverage_start.isoformat(),
        "macro_coverage_end": macro_calendar.coverage_end.isoformat(),
    })
    config = {
        "experiment_id": "EXP-0001",
        "implementation_policy": IMPLEMENTATION_POLICY,
        "validation_policy": VALIDATION_POLICY,
        "contract_master_hash": acquisition_lineage.contract_master_hash,
        "max_settlement_days_forward": acquisition_lineage.max_settlement_days_forward,
        "base_costs": asdict(base_costs),
        "stress_multiple": STRESS_MULTIPLE,
        "primary_horizon_minutes": PRIMARY_HORIZON_MINUTES,
    }

    trial = trial_registry.register(
        experiment_id="EXP-0001", config=config,
        data_snapshot_hash=data_snapshot_hash, git_commit=git_commit,
    )
    trial_count = len(trial_registry.read_all())

    base_book = build_exp0001_evidence_book(bars=materialized, costs=base_costs)
    stress_book = build_exp0001_evidence_book(
        bars=materialized, costs=stressed_costs(base_costs, STRESS_MULTIPLE),
    )
    regimes = build_regime_labels(
        bars=materialized, book=base_book,
        macro_events=macro_calendar.events, horizon_minutes=PRIMARY_HORIZON_MINUTES,
    )
    validation = build_validation_metrics(
        base_book=base_book, stress_1_5x_book=stress_book,
        trial_count=trial_count, regime_labels=regimes,
        data_integrity_ok=True, post_result_parameter_edits=False,
    )
    decision = evaluate_exp0001(validation.metrics)
    verdict = classify_verdict(accepted=decision.accepted, failed_gates=decision.failed_gates)

    candidate_snapshot_hash = _candidate_hash(base_book)
    result_hash = _stable_hash({
        "base": _book_result_payload(base_book),
        "stress_1_5x": _book_result_payload(stress_book),
        "validation": asdict(validation),
        "verdict": verdict,
        "failed_gates": decision.failed_gates,
    })

    record = evidence_ledger.append(
        experiment_id="EXP-0001", trial_id=trial.trial_id, git_commit=git_commit,
        data_snapshot_hash=data_snapshot_hash, candidate_snapshot_hash=candidate_snapshot_hash,
        result_hash=result_hash, config_hash=trial.config_hash,
        verdict=verdict, metrics=asdict(validation.metrics), failed_gates=decision.failed_gates,
    )
    return FormalExpOutcome(
        verdict, decision.failed_gates, trial, validation, record,
        data_snapshot_hash, candidate_snapshot_hash, result_hash,
    )
