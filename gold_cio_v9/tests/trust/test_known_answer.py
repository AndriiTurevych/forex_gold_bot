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
