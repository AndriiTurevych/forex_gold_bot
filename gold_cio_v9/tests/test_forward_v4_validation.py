from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.forward_v4_validation import (
    admission_reason, boundaries, checkpoint, evaluate, partition_statistics,
    policy_hash, verify_checkpoint,
)
from gold_cio_v9.shadow.ledger import HashChainLedger

START = datetime(2026, 9, 10, tzinfo=timezone.utc)


def genesis(tmp_path, scope="PROSPECTIVE_NONBINDING"):
    ledger = HashChainLedger(tmp_path / "ledger.jsonl")
    ledger.append("GENESIS", {"experiment_id": "EXP-0004", "scope": scope,
                              "start_time": START.isoformat(), "engine_commit": "fixed",
                              "protocol_hash": policy_hash()})
    return ledger


def test_no_interim_statistics_and_fixed_end(tmp_path):
    ledger = genesis(tmp_path)
    result = evaluate(ledger, now=START + timedelta(days=179), expected_checkpoint=checkpoint(ledger, "fixed"), engine_commit="fixed")
    assert result["verdict"] == "PENDING" and "statistics" not in result
    result = evaluate(ledger, now=START + timedelta(days=182), expected_checkpoint=checkpoint(ledger, "fixed"), engine_commit="fixed")
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_engineering_evidence_cannot_be_relabelled(tmp_path):
    ledger = genesis(tmp_path, "ENGINEERING_ONLY")
    with pytest.raises(ValueError, match="UNREGISTERED"):
        evaluate(ledger, now=START, expected_checkpoint=checkpoint(ledger, "fixed"), engine_commit="fixed")


def test_external_tip_detects_valid_prefix_truncation(tmp_path):
    ledger = genesis(tmp_path)
    original = ledger.path.read_bytes()
    ledger.append("HEARTBEAT", {"experiment_id": "EXP-0004"})
    trusted = checkpoint(ledger, "fixed")
    ledger.path.write_bytes(original)
    assert ledger.read_verified()  # Internal chain still valid; external anchor must reject it.
    with pytest.raises(ValueError, match="CHECKPOINT"):
        verify_checkpoint(ledger, trusted, "fixed")


def test_engine_change_rejected_by_checkpoint(tmp_path):
    ledger = genesis(tmp_path)
    with pytest.raises(ValueError, match="CHECKPOINT"):
        verify_checkpoint(ledger, checkpoint(ledger, "fixed"), "changed")


def test_calendar_boundary_and_embargo():
    split, end = boundaries(START)
    assert admission_reason(START, START - timedelta(seconds=1))
    assert admission_reason(START, split - timedelta(minutes=60)) == "HOLDOUT_BOUNDARY_EMBARGO"
    assert admission_reason(START, split) is None
    assert admission_reason(START, end - timedelta(minutes=60)) == "REGISTERED_COLLECTION_CLOSED"
    assert admission_reason(START, end + timedelta(days=10))


@pytest.mark.parametrize("gross,passed", [(2., True), (-2., False), (.40, False)])
def test_known_answer_statistics_net_costs_and_stress(gross, passed):
    observations = [(START + timedelta(days=d, hours=h), gross) for d in range(60) for h in (1, 3)]
    result = partition_statistics(observations, START, 90)
    assert result["enough_data"] and result["passed"] is passed
    assert result["mean_net_usd_per_ounce"] == pytest.approx(gross - .35)
    assert result["stress_mean"] == pytest.approx(gross - .525)


def test_large_count_on_one_day_not_enough():
    observations = [(START, 2.)] * 500
    assert partition_statistics(observations, START, 90)["enough_data"] is False


@pytest.mark.parametrize("holdout_gross,expected", [(2., "ACCEPT_NONBINDING"), (-2., "REJECT")])
def test_end_to_end_terminal_verdict_requires_both_partitions(tmp_path, holdout_gross, expected):
    ledger = genesis(tmp_path)
    for offset, gross in ((0, 2.), (90, holdout_gross)):
        for day in range(50):
            for hour in (1, 3):
                when = START + timedelta(days=offset + day, hours=hour)
                target = when + timedelta(minutes=1)
                maturity = target + timedelta(minutes=60)
                sid = f"{offset}-{day}-{hour}"
                ledger.append("DECISION", {"experiment_id": "EXP-0004", "action": "BUY", "signal_id": sid,
                                           "engine_commit": "fixed", "decision_time": when.isoformat(),
                                           "fill_target_time": target.isoformat(), "contract": "GCZ6"})
                ledger.append("SIMULATED_FILL", {"experiment_id": "EXP-0004", "signal_id": sid,
                                                 "fill_time": target.isoformat(), "entry_price": 100.,
                                                 "observed_at": (target + timedelta(minutes=10)).isoformat(), "contract": "GCZ6"})
                ledger.append("OUTCOME", {"experiment_id": "EXP-0004", "signal_id": sid, "horizon_minutes": 60,
                                          "exit_time": maturity.isoformat(), "exit_bar_start": (maturity - timedelta(minutes=1)).isoformat(),
                                          "exit_price": 100. + gross, "gross_price": gross,
                                          "observed_at": (maturity + timedelta(minutes=10)).isoformat(), "contract": "GCZ6"})
    result = evaluate(ledger, now=START + timedelta(days=182), expected_checkpoint=checkpoint(ledger, "fixed"), engine_commit="fixed")
    assert result["verdict"] == expected and result["real_orders_allowed"] is False
    assert result["formal_verdict_allowed"] is False
