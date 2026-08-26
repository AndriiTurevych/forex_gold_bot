"""Transaction-cost model for Gold CIO v9 research.

All components are expressed in *price units per traded unit* before aggregation.
Broker adapters must convert cash commissions/fees into price-equivalent units
using the instrument contract multiplier. This prevents silently adding USD fees
to XAU/GC price moves.
"""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class CostAssumptions:
    spread_price: float
    commission_price_equivalent_round_turn: float
    slippage_price_per_side: float
    stress_multiple: float = 1.0

    def __post_init__(self):
        values = (
            self.spread_price,
            self.commission_price_equivalent_round_turn,
            self.slippage_price_per_side,
            self.stress_multiple,
        )
        if not all(isfinite(v) for v in values):
            raise ValueError("Cost assumptions must be finite")
        if min(
            self.spread_price,
            self.commission_price_equivalent_round_turn,
            self.slippage_price_per_side,
        ) < 0:
            raise ValueError("Costs cannot be negative")
        if self.stress_multiple <= 0:
            raise ValueError("stress_multiple must be positive")


def round_trip_cost_price(a: CostAssumptions) -> float:
    """Return all-in round-trip friction in price units."""
    base = (
        a.spread_price
        + a.commission_price_equivalent_round_turn
        + 2.0 * a.slippage_price_per_side
    )
    return base * a.stress_multiple


def net_pnl_price(gross_pnl_price: float, assumptions: CostAssumptions) -> float:
    """Net price-unit PnL; cash conversion belongs to the instrument adapter."""
    if not isfinite(gross_pnl_price):
        raise ValueError("gross_pnl_price must be finite")
    return gross_pnl_price - round_trip_cost_price(assumptions)


def stressed_costs(base: CostAssumptions, multiple: float) -> CostAssumptions:
    if not isfinite(multiple) or multiple <= 0:
        raise ValueError("multiple must be finite and positive")
    return CostAssumptions(
        spread_price=base.spread_price,
        commission_price_equivalent_round_turn=base.commission_price_equivalent_round_turn,
        slippage_price_per_side=base.slippage_price_per_side,
        stress_multiple=multiple,
    )
