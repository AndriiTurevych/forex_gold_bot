from pathlib import Path

import pytest

from gold_cio_v9.validation.preregistration import (
    PreregistrationPolicyError,
    assert_instrument_scope,
    assert_preregistration_immutable,
    load_lock,
)

LOCK_PATH = Path("gold_cio_v9/experiments/preregistration_locks.yaml")


def test_exp0001_preregistration_matches_locked_blob():
    lock = load_lock(LOCK_PATH, "EXP-0001")
    assert_preregistration_immutable(lock)


def test_exp0001_verdict_is_bound_to_gc():
    lock = load_lock(LOCK_PATH, "EXP-0001")
    assert_instrument_scope(lock, "GC")
    with pytest.raises(PreregistrationPolicyError, match="VERDICT_TRANSFER_FORBIDDEN"):
        assert_instrument_scope(lock, "XAUUSD")


def test_out_of_scope_instrument_is_rejected():
    lock = load_lock(LOCK_PATH, "EXP-0001")
    with pytest.raises(PreregistrationPolicyError, match="INSTRUMENT_OUT_OF_SCOPE"):
        assert_instrument_scope(lock, "SI")
