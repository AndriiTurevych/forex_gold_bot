from datetime import datetime, timedelta, timezone

from gold_cio_v9.live.backtest_crt_tbs import metrics, structural_validation_gate


def test_backtest_metrics_are_r_based_and_cost_stressed():
    trades=[{"r_multiple":2.0},{"r_multiple":-1.0},{"r_multiple":0.0},{"r_multiple":2.0}]
    raw=metrics(trades)
    stress=metrics(trades,cost_stress_r=0.10)
    assert raw["count"]==4
    assert raw["mean_r"]==0.75
    assert raw["profit_factor"]==4.0
    assert raw["win_rate"]==0.5
    assert raw["be_rate"]==0.25
    assert stress["mean_r"]<raw["mean_r"]


def test_structural_gate_blocks_small_samples():
    full={"count":100,"mean_r":0.2,"profit_factor":1.5}
    stress={"count":100,"mean_r":0.1,"profit_factor":1.4}
    holdout={"count":20,"mean_r":0.2,"profit_factor":1.5}
    mc={"p05_final_return":0.1,"p95_max_drawdown":0.05}
    gate=structural_validation_gate(
        metrics_full=full,metrics_cost_005=stress,metrics_holdout=holdout,monte_carlo=mc
    )
    assert gate["structural_backtest_passed"] is False
    assert gate["live_release_allowed"] is False
