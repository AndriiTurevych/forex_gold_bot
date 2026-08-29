import pytest

from gold_cio_v9.execution.adversarial import AdversarialState, evaluate_adversarial
from gold_cio_v9.execution.capital import CapitalState, allocate_capital
from gold_cio_v9.execution.decay import DecayState, RiskMode, evaluate_decay
from gold_cio_v9.execution.emergency import EmergencyCommand, EmergencyState, authorize_emergency_command
from gold_cio_v9.execution.execution_intelligence import ExecutionMode, ExecutionState, choose_execution
from gold_cio_v9.execution.regime_change import RegimeChangeState, evaluate_regime_change
from gold_cio_v9.execution.tca import TCAInput, analyze_tca


def test_decay_full_when_forward_health_is_strong():
    d = evaluate_decay(DecayState(30, 0.15, 1.35, 0.05, True, True))
    assert d.mode is RiskMode.FULL
    assert d.risk_multiplier == 1.0


def test_decay_switches_off_on_negative_edge():
    d = evaluate_decay(DecayState(30, -0.05, 0.95, 0.05, True, True))
    assert d.mode is RiskMode.OFF


def test_execution_health_failure_goes_shadow_only():
    d = evaluate_decay(DecayState(30, 0.20, 1.40, 0.05, True, False))
    assert d.mode is RiskMode.SHADOW_ONLY


def test_adversarial_vetoes_trap():
    d = evaluate_adversarial(AdversarialState(0.2, 0.90, 0.2, 0.2, 2.0, False, True))
    assert not d.approved
    assert d.reason == "TRAP_VETO"


def test_adversarial_approves_clean_setup():
    d = evaluate_adversarial(AdversarialState(0.2, 0.2, 0.2, 0.2, 2.0, False, True))
    assert d.approved


def test_capital_allocation_is_scaled_and_capped():
    d = allocate_capital(CapitalState(0.003, 0.8, 0.9, 0.8, 0.005, 0.1, 0.8))
    assert d.approved
    assert 0 < d.risk_fraction < 0.0025


def test_capital_vetoes_low_margin_headroom():
    d = allocate_capital(CapitalState(0.002, 0.8, 0.9, 0.8, 0.0, 0.0, 0.2))
    assert not d.approved
    assert d.reason == "MARGIN_HEADROOM_VETO"


def test_execution_selector_uses_market_only_for_high_urgency_and_liquidity():
    d = choose_execution(ExecutionState(0.1, 1.0, 0.8, 0.9, 1.0, 0.2))
    assert d.mode is ExecutionMode.MARKET


def test_execution_selector_refuses_when_net_edge_too_small():
    d = choose_execution(ExecutionState(0.1, 1.0, 0.8, 0.5, 0.25, 0.10))
    assert d.mode is ExecutionMode.DO_NOT_ROUTE
    assert d.reason == "NET_EDGE_TOO_SMALL"


def test_regime_transition_derisks():
    d = evaluate_regime_change(RegimeChangeState(1.6, 0.1, 1.1, 1))
    assert not d.stable
    assert d.risk_multiplier == 0.5


def test_severe_regime_transition_stops_risk():
    d = evaluate_regime_change(RegimeChangeState(2.5, 0.1, 1.1, 1))
    assert not d.stable
    assert d.risk_multiplier == 0.0


def test_tca_attributes_buy_execution_drag():
    result = analyze_tca(TCAInput("BUY", 100.0, 100.2, 100.3, 100.5, 102.0, 0.1))
    assert result.gross_alpha_points == pytest.approx(2.0)
    assert result.decision_latency_cost_points == pytest.approx(0.2)
    assert result.submit_latency_cost_points == pytest.approx(0.1)
    assert result.fill_slippage_points == pytest.approx(0.2)
    assert result.realized_net_points == pytest.approx(1.4)
    assert result.execution_drag_points == pytest.approx(0.6)


def test_tca_attributes_sell_execution_drag():
    result = analyze_tca(TCAInput("SELL", 100.0, 99.8, 99.7, 99.5, 98.0, 0.1))
    assert result.gross_alpha_points == pytest.approx(2.0)
    assert result.decision_latency_cost_points == pytest.approx(0.2)
    assert result.submit_latency_cost_points == pytest.approx(0.1)
    assert result.fill_slippage_points == pytest.approx(0.2)
    assert result.realized_net_points == pytest.approx(1.4)


def test_emergency_risk_reduction_is_allowed():
    state = EmergencyState(True, False, False, True)
    assert authorize_emergency_command(EmergencyCommand.FLATTEN, state).allowed


def test_emergency_resume_requires_reconciliation_and_health():
    bad = EmergencyState(False, False, True, True)
    assert not authorize_emergency_command(EmergencyCommand.RESUME, bad).allowed
    good = EmergencyState(False, True, True, True)
    assert authorize_emergency_command(EmergencyCommand.RESUME, good).allowed
