"""Deterministic market-structure primitives for Gold CIO v9.

V1 deliberately uses explicit swing references supplied by the upstream swing detector.
No hindsight relabeling is allowed after the fact.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StructureEvent:
    kind: str          # BOS, CHOCH, MSS
    direction: str     # BULLISH or BEARISH
    broken_level: float
    close_price: float
    displacement_atr: float


def detect_structure_break(
    close_price: float,
    prior_swing_high: float,
    prior_swing_low: float,
    prior_trend: str,
    displacement_atr: float,
    min_displacement_atr: float = 0.8,
) -> Optional[StructureEvent]:
    """Classify a close-through swing break using prior trend and displacement.

    Rules:
    - continuation break in trend direction => BOS
    - opposing break without sufficient displacement => CHOCH
    - opposing break with displacement >= threshold => MSS
    """
    trend = prior_trend.upper()
    if trend not in {"BULLISH", "BEARISH"}:
        raise ValueError("prior_trend must be BULLISH or BEARISH")

    if close_price > prior_swing_high:
        if trend == "BULLISH":
            return StructureEvent("BOS", "BULLISH", prior_swing_high, close_price, displacement_atr)
        kind = "MSS" if displacement_atr >= min_displacement_atr else "CHOCH"
        return StructureEvent(kind, "BULLISH", prior_swing_high, close_price, displacement_atr)

    if close_price < prior_swing_low:
        if trend == "BEARISH":
            return StructureEvent("BOS", "BEARISH", prior_swing_low, close_price, displacement_atr)
        kind = "MSS" if displacement_atr >= min_displacement_atr else "CHOCH"
        return StructureEvent(kind, "BEARISH", prior_swing_low, close_price, displacement_atr)

    return None
