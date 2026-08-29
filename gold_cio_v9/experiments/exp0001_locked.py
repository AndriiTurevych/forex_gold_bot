"""Single source of runtime constants locked before EXP-0001 outcomes."""
from __future__ import annotations

from gold_cio_v9.backtest.costs import CostAssumptions, round_trip_cost_price

IMPLEMENTATION_POLICY_ID = "EXP-0001-BASELINE-POLICY-V5"
VALIDATION_POLICY_ID = "EXP-0001-VALIDATION-POLICY-V5"
HORIZONS_MINUTES = (5, 15, 30, 60)
PRIMARY_HORIZON_MINUTES = 60
ATR_PERIOD = 14
SWING_LEFT_BARS = 2
SWING_RIGHT_BARS = 2
ROLL_BUFFER_DAYS = 5
ROLL_BUFFER_BARS = 0
MAX_SETTLEMENT_DAYS_FORWARD = 365
STRESS_MULTIPLE = 1.5
GC_CONTRACT_MULTIPLIER_USD_PER_POINT = 100.0

LOCKED_BASE_COSTS = CostAssumptions(
    spread_price=0.10,
    commission_price_equivalent_round_turn=0.05,
    slippage_price_per_side=0.10,
    stress_multiple=1.0,
)


def assert_locked_costs(costs: CostAssumptions) -> None:
    if costs != LOCKED_BASE_COSTS:
        raise ValueError("formal EXP-0001 costs diverge from locked baseline V5")
    if abs(round_trip_cost_price(costs) - 0.35) > 1e-12:
        raise RuntimeError("locked EXP-0001 base round-trip cost invariant failed")
