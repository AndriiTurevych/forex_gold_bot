import os

from gold_cio_v9.live.ai_gate import _validate_result, evaluate_context
from gold_cio_v9.live.risk_gate import RiskLimits, evaluate_risk


def _snapshot(spread_points=20):
    point = 0.01
    bid = 4300.00
    ask = bid + spread_points * point
    return {
        "instrument": {
            "symbol": "XAUUSD",
            "point": point,
            "volume_min": 0.01,
            "volume_max": 100.0,
            "volume_step": 0.01,
        },
        "quote": {"event_time": "2026-09-20T09:00:00+00:00", "bid": bid, "ask": ask},
    }


def _analysis():
    return {
        "symbol": "XAUUSD",
        "decision_time": "2026-09-20T09:00:00+00:00",
        "state": "CONFIRMED",
        "action": "BUY",
        "reason": "SHADOW_ICT_CONFIRMED",
        "h1_bias": "LONG",
        "h4_bias": "LONG",
        "entry": 4300.20,
        "stop": 4298.20,
        "tp1": 4302.20,
        "tp2": 4304.20,
        "risk_fraction": 0.0025,
        "volume_lots": 0.10,
        "confidence_score": 82,
        "support_zones": [],
        "resistance_zones": [],
        "ict": {},
    }


def _allow():
    return {
        "decision": "ALLOW",
        "risk_multiplier": 1.0,
        "context_score": 0.8,
        "regime": "TREND",
        "conflict": False,
        "reason_code": "CONTEXT_ALIGNED",
    }


def test_ai_gate_does_not_call_model_without_candidate():
    result = evaluate_context(_snapshot(), {**_analysis(), "state": "WAIT", "action": "ABSTAIN"})
    assert result["decision"] == "BLOCK"
    assert result["status"] == "NOT_CALLED"


def test_ai_gate_fails_closed_when_disabled(monkeypatch):
    monkeypatch.setenv("MIDAS_AI_GATE_ENABLED", "0")
    result = evaluate_context(_snapshot(), _analysis(), api_key="test-key")
    assert result["decision"] == "BLOCK"
    assert result["risk_multiplier"] == 0.0
    assert result["reason_code"] == "AI_GATE_DISABLED"


def test_ai_gate_normalizes_allow_to_full_candidate_risk():
    result = _validate_result(_allow(), "gpt-test")
    assert result["decision"] == "ALLOW"
    assert result["risk_multiplier"] == 1.0


def test_risk_gate_approves_valid_candidate_for_demo_only():
    ai = _validate_result(_allow(), "gpt-test")
    result = evaluate_risk(_snapshot(), _analysis(), ai, limits=RiskLimits())
    assert result["approved"] is True
    assert result["demo_execution_allowed"] is True
    assert result["execution_allowed"] is False
    assert result["real_orders_allowed"] is False


def test_risk_gate_blocks_wide_spread():
    ai = _validate_result(_allow(), "gpt-test")
    result = evaluate_risk(_snapshot(spread_points=120), _analysis(), ai, limits=RiskLimits())
    assert result["approved"] is False
    assert "SPREAD_LIMIT" in result["reasons"]


def test_risk_gate_blocks_after_ai_block():
    ai = {
        "decision": "BLOCK",
        "risk_multiplier": 0.0,
        "context_score": 0.0,
        "regime": "UNKNOWN",
        "conflict": True,
        "reason_code": "CONFLICT",
    }
    result = evaluate_risk(_snapshot(), _analysis(), ai, limits=RiskLimits())
    assert result["approved"] is False
    assert "AI_GATE_BLOCK" in result["reasons"]
