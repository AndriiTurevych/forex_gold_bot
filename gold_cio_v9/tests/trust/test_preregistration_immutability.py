from pathlib import Path

import pytest
yaml = pytest.importorskip("yaml")

from gold_cio_v9.validation.preregistration import (
    PreregistrationPolicyError,
    assert_instrument_scope,
    assert_preregistration_immutable,
    git_blob_sha,
    load_lock,
)

LOCK_PATH = Path("gold_cio_v9/experiments/preregistration_locks.yaml")


def _experiment(experiment_id="EXP-0001"):
    raw = yaml.safe_load(LOCK_PATH.read_text(encoding="utf-8"))
    return raw["experiments"][experiment_id]


def test_exp0001_preregistration_matches_locked_blob():
    lock = load_lock(LOCK_PATH, "EXP-0001")
    assert_preregistration_immutable(lock)


def test_exp0001_active_baseline_policy_v5_matches_locked_blob():
    policy = _experiment()["implementation_policy"]
    assert policy["id"] == "EXP-0001-BASELINE-POLICY-V5"
    assert policy["status"] == "LOCKED_BEFORE_OUTCOMES"
    assert policy["post_outcome_modification_allowed"] is False
    assert git_blob_sha(policy["path"]) == policy["registered_blob_sha"]


def test_superseded_baseline_policies_remain_hash_auditable():
    history = _experiment()["implementation_policy_history"]
    assert [p["id"] for p in history] == [
        "EXP-0001-BASELINE-POLICY-V1",
        "EXP-0001-BASELINE-POLICY-V2",
        "EXP-0001-BASELINE-POLICY-V3",
        "EXP-0001-BASELINE-POLICY-V4",
    ]
    for policy in history:
        assert policy["status"] == "SUPERSEDED_BEFORE_OUTCOMES"
        assert git_blob_sha(policy["path"]) == policy["registered_blob_sha"]


def test_exp0001_active_validation_policy_v5_matches_locked_blob():
    policy = _experiment()["validation_policy"]
    assert policy["id"] == "EXP-0001-VALIDATION-POLICY-V5"
    assert policy["status"] == "LOCKED_BEFORE_OUTCOMES"
    assert policy["post_outcome_modification_allowed"] is False
    assert git_blob_sha(policy["path"]) == policy["registered_blob_sha"]


def test_superseded_validation_policies_remain_hash_auditable():
    history = _experiment()["validation_policy_history"]
    assert [p["id"] for p in history] == [
        "EXP-0001-VALIDATION-POLICY-V1",
        "EXP-0001-VALIDATION-POLICY-V2",
        "EXP-0001-VALIDATION-POLICY-V3",
        "EXP-0001-VALIDATION-POLICY-V4",
    ]
    for policy in history:
        assert policy["status"] == "SUPERSEDED_BEFORE_OUTCOMES"
        assert git_blob_sha(policy["path"]) == policy["registered_blob_sha"]


def test_exp0001_verdict_is_bound_to_gc():
    lock = load_lock(LOCK_PATH, "EXP-0001")
    assert_instrument_scope(lock, "GC")
    with pytest.raises(PreregistrationPolicyError, match="VERDICT_TRANSFER_FORBIDDEN"):
        assert_instrument_scope(lock, "XAUUSD")


def test_exp0001_closure_is_immutable_and_negative():
    closure = _experiment()["closure"]
    assert closure["status"] == "CLOSED_NONBINDING"
    assert closure["verdict"] == "INSUFFICIENT_DATA"
    assert closure["post_outcome_modification_allowed"] is False
    assert git_blob_sha(closure["path"]) == closure["registered_blob_sha"]


def test_exp0002_preregistration_matches_locked_blob_before_outcomes():
    experiment = _experiment("EXP-0002")
    assert experiment["status"] == "LOCKED_BEFORE_OUTCOMES"
    assert experiment["outcomes_computed"] is False
    assert experiment["post_outcome_modification_allowed"] is False
    feasibility = experiment["data_feasibility"]
    assert feasibility["status"] == "BLOCKED_ENTITLEMENT"
    assert feasibility["outcome_computation_allowed"] is False
    assert git_blob_sha(feasibility["path"]) == feasibility["registered_blob_sha"]
    dry_run = experiment["available_tail_dry_run"]
    assert dry_run["status"] == "SEALED_OUTCOME_FREE"
    assert dry_run["formal_verdict_allowed"] is False
    assert git_blob_sha(dry_run["path"]) == dry_run["registered_blob_sha"]
    lock = load_lock(LOCK_PATH, "EXP-0002")
    assert_preregistration_immutable(lock)


def test_out_of_scope_instrument_is_rejected():
    lock = load_lock(LOCK_PATH, "EXP-0001")
    with pytest.raises(PreregistrationPolicyError, match="INSTRUMENT_OUT_OF_SCOPE"):
        assert_instrument_scope(lock, "SI")
