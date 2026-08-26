from datetime import date, datetime, time, timedelta, timezone

import pytest

from gold_cio_v9.backtest.costs import CostAssumptions, net_pnl, round_trip_cost
from gold_cio_v9.features.store import FeatureRow, PointInTimeFeatureStore
from gold_cio_v9.ict_engine.features import Bar, detect_liquidity_sweep
from gold_cio_v9.ict_engine.sessions import SessionWindow, session_liquidity
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


def test_risk_gate_fails_closed_on_nan():
    state = RiskState(float("nan"), 0.0, 0.0, True, True, True, False)
    decision = evaluate(state)
    assert not decision.approved
    assert decision.reason == "INVALID_RISK_FRACTION"


def test_risk_gate_rejects_negative_loss_fraction():
    state = RiskState(0.001, -0.01, 0.0, True, True, True, False)
    decision = evaluate(state)
    assert not decision.approved
    assert decision.reason == "INVALID_DAILY_LOSS"


def test_cost_stress_is_applied():
    assumptions = CostAssumptions(0.2, 0.1, 0.05, 1.5)
    assert round_trip_cost(assumptions) == pytest.approx(0.6)
    assert net_pnl(2.0, assumptions) == pytest.approx(1.4)


def test_cost_model_rejects_non_finite_input():
    with pytest.raises(ValueError):
        CostAssumptions(float("nan"), 0.1, 0.05)
    with pytest.raises(ValueError):
        net_pnl(float("inf"), CostAssumptions(0.2, 0.1, 0.05))


def test_point_in_time_store_blocks_future_availability():
    t0 = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    store = PointInTimeFeatureStore()
    store.append(FeatureRow(t0, t0, {"x": 1}))
    store.append(FeatureRow(t0 + timedelta(minutes=1), t0 + timedelta(minutes=2), {"x": 2}))
    latest = store.latest(t0 + timedelta(minutes=1))
    assert latest is not None
    assert latest.values["x"] == 1


def test_point_in_time_store_rejects_naive_timestamps():
    naive = datetime(2026, 8, 26, 10, 0)
    with pytest.raises(ValueError):
        FeatureRow(naive, naive, {"x": 1})


def test_overnight_session_uses_start_date_anchor_without_cross_session_leakage():
    window = SessionWindow("OVERNIGHT", time(22, 0), time(2, 0))
    rows = [
        (datetime(2026, 8, 26, 23, 0, tzinfo=timezone.utc), 101.0, 99.0),
        (datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc), 103.0, 98.0),
        (datetime(2026, 8, 27, 23, 0, tzinfo=timezone.utc), 999.0, 1.0),
    ]
    result = session_liquidity(rows, window, date(2026, 8, 26))
    assert result is not None
    assert result.high == 103.0
    assert result.low == 98.0
