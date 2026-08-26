from datetime import datetime, timedelta

from gold_cio_v9.backtest.costs import CostAssumptions, net_pnl, round_trip_cost
from gold_cio_v9.features.store import FeatureRow, PointInTimeFeatureStore
from gold_cio_v9.ict_engine.features import Bar, detect_liquidity_sweep
from gold_cio_v9.risk.gate import RiskState, evaluate


def test_bsl_sweep_requires_close_back_below_level():
    bar = Bar("t", 100.0, 102.0, 99.5, 100.5)
    sweep = detect_liquidity_sweep(bar, reference_high=101.0, reference_low=98.0)
    assert sweep is not None and sweep.side == "BSL"


def test_risk_gate_vetoes_stale_data():
    state = RiskState(0.0025, 0.0, 0.0, True, False, True, False)
    decision = evaluate(state)
    assert not decision.approved
    assert decision.reason == "STALE_DATA"


def test_cost_stress_is_applied():
    assumptions = CostAssumptions(0.2, 0.1, 0.05, 1.5)
    assert round_trip_cost(assumptions) == 0.6
    assert net_pnl(2.0, assumptions) == 1.4


def test_point_in_time_store_blocks_future_availability():
    t0 = datetime(2026, 8, 26, 10, 0)
    store = PointInTimeFeatureStore()
    store.append(FeatureRow(t0, t0, {"x": 1}))
    store.append(FeatureRow(t0 + timedelta(minutes=1), t0 + timedelta(minutes=2), {"x": 2}))
    latest = store.latest(t0 + timedelta(minutes=1))
    assert latest is not None
    assert latest.values["x"] == 1
