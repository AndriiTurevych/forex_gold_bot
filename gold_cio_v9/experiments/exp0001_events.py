"""Point-in-time event extraction for EXP-0001.

Transforms closed bars plus already-known reference levels into deterministic sweep,
MSS and FVG candidates. The module deliberately does not choose/optimize HTF
location or liquidity references; those remain upstream preregistered features.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from gold_cio_v9.experiments.exp0001_signal import FVGZone, TimedStructure, TimedSweep
from gold_cio_v9.ict_engine.features import Bar, bearish_fvg, bullish_fvg, detect_liquidity_sweep, displacement_atr
from gold_cio_v9.ict_engine.structure import detect_structure_break


@dataclass(frozen=True)
class TimedBar:
    event_time: datetime
    bar: Bar


def extract_sweep(current: TimedBar, *, reference_high: float, reference_low: float) -> TimedSweep | None:
    sweep = detect_liquidity_sweep(current.bar, reference_high, reference_low)
    return None if sweep is None else TimedSweep(current.event_time, sweep)


def extract_mss(
    current: TimedBar,
    *,
    prior_swing_high: float,
    prior_swing_low: float,
    prior_trend: str,
    atr: float,
    min_displacement_atr: float = 0.8,
) -> TimedStructure | None:
    disp = displacement_atr(current.bar, atr)
    event = detect_structure_break(
        current.bar.close,
        prior_swing_high,
        prior_swing_low,
        prior_trend,
        disp,
        min_displacement_atr=min_displacement_atr,
    )
    if event is None or event.kind != "MSS":
        return None
    return TimedStructure(current.event_time, event)


def extract_fvg(first: TimedBar, middle: TimedBar, third: TimedBar, *, direction: str) -> FVGZone | None:
    """Confirm an FVG only when the third candle has closed.

    middle is accepted explicitly to enforce a true three-candle sequence even
    though gap geometry depends only on candles one and three.
    """
    if not (first.event_time < middle.event_time < third.event_time):
        raise ValueError("FVG candles must be strictly time ordered")
    d = direction.upper()
    if d == "BULLISH":
        zone = bullish_fvg(first.bar, third.bar)
    elif d == "BEARISH":
        zone = bearish_fvg(first.bar, third.bar)
    else:
        raise ValueError("direction must be BULLISH or BEARISH")
    if zone is None:
        return None
    low, high = zone
    return FVGZone(third.event_time, low, high, d)
