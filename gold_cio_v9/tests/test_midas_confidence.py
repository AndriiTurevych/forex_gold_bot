from datetime import datetime, timezone

import pytest

from gold_cio_v9.shadow.calibration import record_outcome, summarize_outcomes
from gold_cio_v9.shadow.ledger import HashChainLedger
from gold_cio_v9.strategies.confidence import (
    CalibrationEvidence,
    ConfidenceFactors,
    score_confidence,
)


def factors(**overrides):
    values = dict(
        trend=0.8, location=0.9, structure=0.8, entry_quality=0.7,
        reward_risk=0.8, macro=0.6, data_quality=1.0, model_agreement=0.8,
    )
    values.update(overrides)
    return ConfidenceFactors(**values)


def test_unconfirmed_setup_is_capped_and_not_called_probability():
    result = score_confidence(factors(), mss_confirmed=False, retest_confirmed=False, event_lock=False)
    assert result.state == "ARMED"
    assert result.confidence_score <= 59
    assert result.calibrated_probability is None
    assert result.calibration_status == "UNCALIBRATED"


def test_confirmed_but_small_sample_stays_uncalibrated():
    result = score_confidence(
        factors(), mss_confirmed=True, retest_confirmed=True, event_lock=False,
        evidence=CalibrationEvidence(wins=68, losses=31),
    )
    assert result.state == "CONFIRMED"
    assert result.sample_size == 99
    assert result.calibrated_probability is None


def test_probability_requires_one_hundred_resolved_outcomes():
    result = score_confidence(
        factors(), mss_confirmed=True, retest_confirmed=True, event_lock=False,
        evidence=CalibrationEvidence(wins=68, losses=32),
    )
    assert result.calibration_status == "CALIBRATED"
    assert result.calibrated_probability == pytest.approx(69 / 102)


def test_event_lock_is_absolute_veto():
    result = score_confidence(factors(), mss_confirmed=True, retest_confirmed=True, event_lock=True)
    assert result.state == "VETO"
    assert result.confidence_score == 0


def test_invalid_factor_fails_closed():
    with pytest.raises(ValueError):
        score_confidence(factors(trend=1.1), mss_confirmed=True, retest_confirmed=True, event_lock=False)


def test_hash_chained_outcomes_produce_calibration_metrics(tmp_path):
    ledger = HashChainLedger(tmp_path / "midas.jsonl")
    record_outcome(ledger, signal_id="a", realized_r=2.0, predicted_probability=0.7)
    record_outcome(ledger, signal_id="b", realized_r=-1.0, predicted_probability=0.6)
    summary = summarize_outcomes(ledger.read_verified())
    assert summary.resolved == 2
    assert summary.wins == 1
    assert summary.win_rate == 0.5
    assert summary.expectancy_r == 0.5
    assert summary.brier_score == pytest.approx(((0.7 - 1) ** 2 + 0.6 ** 2) / 2)
