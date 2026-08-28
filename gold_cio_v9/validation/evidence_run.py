"""Ledger-first evidence orchestration for EXP-0001.

The orchestrator receives already-produced OOS/holdout statistics, evaluates the
locked acceptance constitution, and persists the verdict before returning it to
callers. This keeps decision publication ahead of human inspection.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from gold_cio_v9.backtest.runner import BacktestResult
from gold_cio_v9.validation.acceptance import ValidationMetrics, evaluate_exp0001
from gold_cio_v9.validation.ledger import EvidenceLedger, EvidenceRecord


INSUFFICIENT_EVIDENCE_GATES = frozenset({"RAW_OOS_SAMPLE", "DATA_RESOLUTION_RISK"})


@dataclass(frozen=True)
class EvidenceOutcome:
    verdict: str
    failed_gates: tuple[str, ...]
    ledger_record: EvidenceRecord


def classify_verdict(*, accepted: bool, failed_gates: tuple[str, ...]) -> str:
    """Return ACCEPT, REJECT or INSUFFICIENT_DATA without human discretion.

    A run cannot be promoted when the precommitted resolved-sample minimum is not
    met or when bar-resolution ambiguity is material. Those states are evidence
    insufficiency, not proof of alpha failure. All failed gates are still persisted
    so weak economics observed in an underpowered run remain visible.
    """
    if accepted:
        return "ACCEPT"
    if any(gate in INSUFFICIENT_EVIDENCE_GATES for gate in failed_gates):
        return "INSUFFICIENT_DATA"
    return "REJECT"


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
    verdict = classify_verdict(accepted=decision.accepted, failed_gates=decision.failed_gates)
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
