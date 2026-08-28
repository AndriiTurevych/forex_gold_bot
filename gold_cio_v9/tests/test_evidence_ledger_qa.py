import json
from pathlib import Path

import pytest

from gold_cio_v9.validation.ledger import EvidenceLedger


def _append(ledger: EvidenceLedger, verdict: str, trial_id: str = "trial"):
    return ledger.append(
        experiment_id="EXP-0001",
        trial_id=trial_id,
        git_commit="abc123",
        data_snapshot_hash="d" * 64,
        candidate_snapshot_hash="c" * 64,
        result_hash="r" * 64,
        config_hash="cfg",
        verdict=verdict,
        metrics={"x": 1.0},
        failed_gates=(),
    )


def test_ledger_accepts_all_three_governance_verdicts(tmp_path: Path):
    ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
    for idx, verdict in enumerate(("ACCEPT", "REJECT", "INSUFFICIENT_DATA"), start=1):
        _append(ledger, verdict, f"trial-{idx}")
    assert [row["verdict"] for row in ledger.read_all()] == [
        "ACCEPT",
        "REJECT",
        "INSUFFICIENT_DATA",
    ]


def test_ledger_rejects_unknown_verdict_fail_closed(tmp_path: Path):
    ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
    with pytest.raises(ValueError, match="verdict"):
        _append(ledger, "MAYBE")
    assert ledger.read_all() == []


def test_ledger_is_append_only_and_each_row_has_record_hash(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    ledger = EvidenceLedger(path)
    _append(ledger, "REJECT", "trial-1")
    first_bytes = path.read_bytes()
    _append(ledger, "INSUFFICIENT_DATA", "trial-2")
    second_bytes = path.read_bytes()

    assert second_bytes.startswith(first_bytes)
    rows = [json.loads(line) for line in second_bytes.decode("utf-8").splitlines() if line]
    assert len(rows) == 2
    assert all(len(row["record_hash"]) == 64 for row in rows)
    assert rows[0]["trial_id"] == "trial-1"
    assert rows[1]["trial_id"] == "trial-2"


def test_failed_gates_round_trip_without_mutation(tmp_path: Path):
    ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
    ledger.append(
        experiment_id="EXP-0001",
        trial_id="trial-risk",
        git_commit="abc123",
        data_snapshot_hash="d" * 64,
        candidate_snapshot_hash="c" * 64,
        result_hash="r" * 64,
        config_hash="cfg",
        verdict="INSUFFICIENT_DATA",
        metrics={"ambiguity_rate": 0.08},
        failed_gates=("OOS_EXPECTANCY", "DATA_RESOLUTION_RISK"),
    )
    row = ledger.read_all()[0]
    assert row["failed_gates"] == ["OOS_EXPECTANCY", "DATA_RESOLUTION_RISK"]
    assert row["metrics"]["ambiguity_rate"] == 0.08
