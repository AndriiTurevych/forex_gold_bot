from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from gold_cio_v9.backtest.costs import round_trip_cost_price
from gold_cio_v9.experiments.exp0001_locked import (
    ATR_PERIOD,
    GC_CONTRACT_MULTIPLIER_USD_PER_POINT,
    HORIZONS_MINUTES,
    IMPLEMENTATION_POLICY_ID,
    LOCKED_BASE_COSTS,
    MAX_SETTLEMENT_DAYS_FORWARD,
    PRIMARY_HORIZON_MINUTES,
    ROLL_BUFFER_BARS,
    ROLL_BUFFER_DAYS,
    STRESS_MULTIPLE,
    SWING_LEFT_BARS,
    SWING_RIGHT_BARS,
    VALIDATION_POLICY_ID,
)


def _policy(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def test_runtime_constants_match_locked_baseline_v5_exactly():
    p = _policy("gold_cio_v9/experiments/EXP-0001-BASELINE-POLICY-V5.yaml")
    assert p["id"] == IMPLEMENTATION_POLICY_ID
    assert p["causal_inputs"]["atr_period"] == ATR_PERIOD
    assert p["causal_inputs"]["swing_left_bars"] == SWING_LEFT_BARS
    assert p["causal_inputs"]["swing_right_bars"] == SWING_RIGHT_BARS
    assert tuple(p["labels"]["horizons_minutes"]) == HORIZONS_MINUTES
    assert p["futures_chain"]["roll_buffer_days"] == ROLL_BUFFER_DAYS
    assert p["execution"]["roll_boundary_signal_blackout_bars"] == ROLL_BUFFER_BARS
    assert p["futures_chain"]["max_settlement_days_forward"] == MAX_SETTLEMENT_DAYS_FORWARD
    assert p["costs"]["contract_multiplier_usd_per_point"] == GC_CONTRACT_MULTIPLIER_USD_PER_POINT
    assert p["costs"]["spread_price"] == LOCKED_BASE_COSTS.spread_price
    assert p["costs"]["commission_price_equivalent_round_turn"] == LOCKED_BASE_COSTS.commission_price_equivalent_round_turn
    assert p["costs"]["slippage_price_per_side"] == LOCKED_BASE_COSTS.slippage_price_per_side
    assert p["costs"]["mandatory_stress_multiple"] == STRESS_MULTIPLE
    assert p["costs"]["base_round_trip_cost_price"] == pytest.approx(round_trip_cost_price(LOCKED_BASE_COSTS))
    assert p["costs"]["base_round_trip_cost_usd_per_contract"] == pytest.approx(round_trip_cost_price(LOCKED_BASE_COSTS) * GC_CONTRACT_MULTIPLIER_USD_PER_POINT)


def test_runtime_validation_identity_matches_locked_v5():
    p = _policy("gold_cio_v9/experiments/EXP-0001-VALIDATION-POLICY-V5.yaml")
    assert p["id"] == VALIDATION_POLICY_ID
    assert p["verdict"]["promotion_metrics_use_horizon_minutes"] == PRIMARY_HORIZON_MINUTES
    assert p["costs"]["mandatory_stress_multiple"] == STRESS_MULTIPLE
