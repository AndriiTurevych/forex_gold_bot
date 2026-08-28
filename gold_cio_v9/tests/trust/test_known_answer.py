from dataclasses import replace

from gold_cio_v9.validation.acceptance import ValidationMetrics, evaluate_exp0001


def good_metrics():
    return ValidationMetrics(0.25, 1.6, 240, True, True, 0.18, True, 0.10, 0.08, True, True, False, True, False)


def test_injected_edge_is_accepted():
    d = evaluate_exp0001(good_metrics())
    assert d.accepted
    assert d.failed_gates == ()


def test_noise_is_rejected():
    m = ValidationMetrics(0.0, 1.0, 240, True, True, 0.0, False, 0.45, -0.02, False, False, False, True, False)
    d = evaluate_exp0001(m)
    assert not d.accepted
    assert "OOS_EXPECTANCY" in d.failed_gates
    assert "DEFLATED_SHARPE" in d.failed_gates


def test_outlier_concentrated_edge_is_rejected():
    m = replace(good_metrics(), top_trade_removal_ok=False, concentration_ok=False)
    d = evaluate_exp0001(m)
    assert not d.accepted
    assert "TOP_TRADE_DEPENDENCE" in d.failed_gates
    assert "PNL_CONCENTRATION" in d.failed_gates


def test_edge_that_dies_under_cost_stress_is_rejected():
    m = replace(good_metrics(), expectancy_cost_1_5x=0.0)
    d = evaluate_exp0001(m)
    assert not d.accepted
    assert "COST_STRESS_1_5X" in d.failed_gates


def test_regime_fragile_edge_is_rejected():
    m = replace(good_metrics(), catastrophic_regime=True)
    d = evaluate_exp0001(m)
    assert not d.accepted
    assert "CATASTROPHIC_REGIME" in d.failed_gates


def test_ambiguous_trades_do_not_rescue_sample_size():
    # 199 resolved + any number ambiguous is still below the >=200 resolved threshold.
    m = replace(good_metrics(), raw_oos_setups=199, ambiguous_oos_setups=20, ambiguity_rate=20 / 219)
    d = evaluate_exp0001(m)
    assert not d.accepted
    assert "RAW_OOS_SAMPLE" in d.failed_gates


def test_excessive_ambiguity_is_data_resolution_risk():
    m = replace(good_metrics(), ambiguous_oos_setups=20, ambiguity_rate=20 / 260)
    d = evaluate_exp0001(m)
    assert not d.accepted
    assert "DATA_RESOLUTION_RISK" in d.failed_gates
