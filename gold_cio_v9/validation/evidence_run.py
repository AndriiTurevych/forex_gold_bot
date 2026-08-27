"""Ledger-first evidence orchestration for EXP-0001.

The orchestrator receives already-produced OOS/holdout statistics, evaluates the
locked acceptance constitution, and persists the verdict before returning it to
callers. This keeps decision publication ahead of human inspection.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from gold_cio_v9.backtest.runner import BacktestResult
from gold_cio_v9.validation.acceptance import ValidationMetrics, evaluate_exp0001
from gold_cio_v9.validation.ledger import EvidenceLedger, EvidenceRecord


@dataclass(frozen=True)
class EvidenceOutcome:
    verdict: str
    failed_gates: tuple[str, ...]
    ledger_record: EvidenceRecord


def publish_exp0001_verdict(
    *,
    result: BacktestResult,
    validation: ValidationMetrics,
    ledger: EvidenceLedger,
    trial_id: str,
    git_commit: str,
    config_hash: str,
) -> EvidenceOutcome:
    """Evaluate and persist EXP-0001 before returning any verdict."""
    decision = evaluate_exp0001(validation)
    verdict = "ACCEPT" if decision.accepted else "REJECT"
    record = ledger.append(
        experiment_id="EXP-0001",
        trial_id=trial_id,
        git_commit=git_commit,
        data_snapshot_hash=result.data_snapshot_hash,
        candidate_snapshot_hash=result.candidate_snapshot_hash,
        result_hash=result.result_hash,
        config_hash=config_hash,
        verdict=verdict,
        metrics=asdict(validation),
        failed_gates=decision.failed_gates,
    )
    return EvidenceOutcome(verdict, decision.failed_gates, record)
