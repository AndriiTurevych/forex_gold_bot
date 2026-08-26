"""Transaction-cost model for Gold CIO v9 research.

Backtests must never report frictionless headline performance.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CostAssumptions:
    spread: float
    commission_round_turn: float
    slippage_per_side: float
    stress_multiple: float = 1.0

    def __post_init__(self):
        if min(self.spread, self.commission_round_turn, self.slippage_per_side) < 0:
            raise ValueError("Costs cannot be negative")
        if self.stress_multiple <= 0:
            raise ValueError("stress_multiple must be positive")


def round_trip_cost(a: CostAssumptions) -> float:
    base = a.spread + a.commission_round_turn + 2.0 * a.slippage_per_side
    return base * a.stress_multiple


def net_pnl(gross_pnl: float, assumptions: CostAssumptions) -> float:
    return gross_pnl - round_trip_cost(assumptions)


def stressed_costs(base: CostAssumptions, multiple: float) -> CostAssumptions:
    return CostAssumptions(
        spread=base.spread,
        commission_round_turn=base.commission_round_turn,
        slippage_per_side=base.slippage_per_side,
        stress_multiple=multiple,
    )
