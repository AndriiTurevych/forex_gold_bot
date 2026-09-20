from datetime import datetime, timedelta, timezone

from gold_cio_v9.live.backtest_crt_tbs import metrics


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
