from dataclasses import replace
from pathlib import Path

from gold_cio_v9.backtest.runner import BacktestResult
from gold_cio_v9.validation.acceptance import ValidationMetrics
from gold_cio_v9.validation.evidence_run import publish_exp0001_verdict
from gold_cio_v9.validation.ledger import EvidenceLedger


def _result():
    return BacktestResult(
        instrument="GC",
        data_snapshot_hash="d" * 64,
        candidate_snapshot_hash="c" * 64,
        result_hash="r" * 64,
        trades=(),
    )


def _passing_metrics():
    return ValidationMetrics(
        oos_expectancy=0.2,
        oos_profit_factor=1.5,
        raw_oos_setups=250,
        effective_sample_ok=True,
        walk_forward_stable=True,
        holdout_expectancy=0.1,
        dsr_ok=True,
        pbo=0.10,
        expectancy_cost_1_5x=0.05,
        top_trade_removal_ok=True,
        concentration_ok=True,
        catastrophic_regime=False,
        data_integrity_ok=True,
        post_result_parameter_edits=False,
    )


def test_accept_is_written_before_return(tmp_path: Path):
    ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
    outcome = publish_exp0001_verdict(
        result=_result(),
        validation=_passing_metrics(),
        ledger=ledger,
        trial_id="trial-1",
        git_commit="abc123",
        config_hash="cfg",
    )
    rows = ledger.read_all()
    assert outcome.verdict == "ACCEPT"
    assert len(rows) == 1
    assert rows[0]["verdict"] == "ACCEPT"


def test_failed_gate_is_persisted(tmp_path: Path):
    ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
    metrics = replace(_passing_metrics(), oos_profit_factor=1.29)
    outcome = publish_exp0001_verdict(
        result=_result(),
        validation=metrics,
        ledger=ledger,
        trial_id="trial-2",
        git_commit="abc123",
        config_hash="cfg",
    )
    assert outcome.verdict == "REJECT"
    assert "OOS_PROFIT_FACTOR" in outcome.failed_gates
    assert "OOS_PROFIT_FACTOR" in ledger.read_all()[0]["failed_gates"]
