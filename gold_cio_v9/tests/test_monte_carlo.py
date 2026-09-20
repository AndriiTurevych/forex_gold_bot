from gold_cio_v9.live.monte_carlo import monte_carlo_r, validation_gate


def test_empirical_monte_carlo_is_deterministic():
    values=[2,-1,0,2,-1,2,-1,0,2,-1]*25
    a=monte_carlo_r(values,paths=2000,horizon_trades=100,block_size=5,seed=7)
    b=monte_carlo_r(values,paths=2000,horizon_trades=100,block_size=5,seed=7)
    assert a==b
    assert a["real_orders_allowed"] is False


def test_gate_requires_200_resolved_trades():
    mc=monte_carlo_r([2,-1,0,2,-1]*20,paths=1000,horizon_trades=50,seed=3)
    gate=validation_gate(mc)
    assert gate["demo_validated"] is False
    assert "MINIMUM_SAMPLE_NOT_REACHED" in gate["reasons"]
    assert gate["live_release_allowed"] is False
