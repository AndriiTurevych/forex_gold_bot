from datetime import datetime, timedelta, timezone

from gold_cio_v9.experiments.exp0001_signal import FVGZone, TimedStructure, TimedSweep
from gold_cio_v9.ict_engine.features import Bar, Sweep
from gold_cio_v9.ict_engine.structure import StructureEvent
from gold_cio_v9.risk.gate import RiskState
from gold_cio_v9.strategies.confidence import CalibrationEvidence, ConfidenceFactors
from gold_cio_v9.strategies.midas_v10_lean import MidasInputs, evaluate_midas


BASE = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def valid_inputs(**overrides):
    values = dict(
        decision_time=BASE,
        h1_bias="LONG",
        h4_bias="LONG",
        trades_today=0,
        equity=100_000.0,
        point_value=1.0,
        atr=10.0,
        risk_state=RiskState(
            risk_fraction=0.0025,
            daily_loss_fraction=0.0,
            weekly_drawdown_fraction=0.0,
            spread_ok=True,
            data_fresh=True,
            feed_agreement=True,
            high_impact_event_lock=False,
        ),
        htf_location_ok=True,
        sweep=TimedSweep(BASE - timedelta(minutes=45), Sweep("SSL", 4300.0, 5.0)),
        structure=TimedStructure(
            BASE - timedelta(minutes=30),
            StructureEvent("MSS", "BULLISH", 4310.0, 4315.0, 1.3),
        ),
        zone=FVGZone(BASE - timedelta(minutes=15), 4308.0, 4312.0, "BULLISH"),
        retest_bar=Bar(BASE.isoformat(), 4312.0, 4313.0, 4309.0, 4311.0),
    )
    values.update(overrides)
    return MidasInputs(**values)


def test_valid_signal_is_sized_but_never_live():
    decision = evaluate_midas(valid_inputs())
    assert decision.action == "BUY"
    assert decision.reason == "SHADOW_APPROVED"
    assert decision.cash_risk == 250.0
    assert decision.tp2 > decision.tp1 > decision.entry > decision.stop
    assert decision.execution_allowed is False


def test_regime_disagreement_abstains():
    assert evaluate_midas(valid_inputs(h4_bias="SHORT")).reason == "HTF_REGIME_DISAGREEMENT"


def test_event_lock_abstains():
    state = valid_inputs().risk_state
    locked = RiskState(**{**state.__dict__, "high_impact_event_lock": True})
    assert evaluate_midas(valid_inputs(risk_state=locked)).reason == "EVENT_LOCK"


def test_midas_daily_loss_lock_is_half_percent():
    state = valid_inputs().risk_state
    locked = RiskState(**{**state.__dict__, "daily_loss_fraction": 0.005})
    assert evaluate_midas(valid_inputs(risk_state=locked)).reason == "MIDAS_DAILY_LOSS_LOCK"


def test_third_trade_and_outside_session_abstain():
    assert evaluate_midas(valid_inputs(trades_today=2)).reason == "DAILY_TRADE_LIMIT"
    night = BASE.replace(hour=3)
    assert evaluate_midas(valid_inputs(decision_time=night)).reason == "OUTSIDE_LONDON_NEW_YORK_SESSION"


def test_incomplete_sequence_and_naive_time_abstain():
    bad_zone = FVGZone(BASE - timedelta(hours=1), 4308.0, 4312.0, "BULLISH")
    assert evaluate_midas(valid_inputs(zone=bad_zone)).reason == "INCOMPLETE_ICT_SEQUENCE"
    assert evaluate_midas(valid_inputs(decision_time=BASE.replace(tzinfo=None))).reason == "INVALID_DECISION_TIME"


def test_approved_decision_exposes_score_but_not_fake_probability():
    scored = valid_inputs(
        confidence_factors=ConfidenceFactors(
            trend=0.8, location=0.9, structure=0.8, entry_quality=0.7,
            reward_risk=0.8, macro=0.6, data_quality=1.0, model_agreement=0.8,
        ),
        calibration_evidence=CalibrationEvidence(wins=0, losses=0),
    )
    decision = evaluate_midas(scored)
    assert decision.state == "CONFIRMED"
    assert decision.confidence_score > 0
    assert decision.calibrated_probability is None
    assert decision.calibration_status == "UNCALIBRATED"
