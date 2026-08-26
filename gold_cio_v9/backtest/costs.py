"""Transaction-cost model for Gold CIO v9 research.

Backtests must never report frictionless headline performance.
"""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class CostAssumptions:
    spread: float
    commission_round_turn: float
    slippage_per_side: float
    stress_multiple: float = 1.0

    def __post_init__(self):
        values = (self.spread, self.commission_round_turn, self.slippage_per_side, self.stress_multiple)
        if not all(isfinite(v) for v in values):
            raise ValueError("Cost assumptions must be finite")
        if min(self.spread, self.commission_round_turn, self.slippage_per_side) < 0:
            raise ValueError("Costs cannot be negative")
        if self.stress_multiple <= 0:
            raise ValueError("stress_multiple must be positive")


def round_trip_cost(a: CostAssumptions) -> float:
    base = a.spread + a.commission_round_turn + 2.0 * a.slippage_per_side
    return base * a.stress_multiple


def net_pnl(gross_pnl: float, assumptions: CostAssumptions) -> float:
    if not isfinite(gross_pnl):
        raise ValueError("gross_pnl must be finite")
    return gross_pnl - round_trip_cost(assumptions)


def stressed_costs(base: CostAssumptions, multiple: float) -> CostAssumptions:
    if not isfinite(multiple) or multiple <= 0:
        raise ValueError("multiple must be finite and positive")
    return CostAssumptions(
        spread=base.spread,
        commission_round_turn=base.commission_round_turn,
        slippage_per_side=base.slippage_per_side,
        stress_multiple=multiple,
    )
