"""Deterministic, point-in-time ICT feature primitives for Gold CIO v9.

All functions consume only current/past observations. No discretionary chart labels.
Malformed/non-finite market data fails closed rather than silently becoming a feature.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Optional


@dataclass(frozen=True)
class Bar:
    ts: str
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Sweep:
    side: str  # BSL or SSL
    level: float
    depth: float


def _validate_bar(bar: Bar) -> None:
    values = (bar.open, bar.high, bar.low, bar.close)
    if not all(isfinite(v) for v in values):
        raise ValueError("bar OHLC values must be finite")
    if bar.high < bar.low:
        raise ValueError("bar high cannot be below low")
    if not bar.low <= bar.open <= bar.high:
        raise ValueError("bar open must lie within [low, high]")
    if not bar.low <= bar.close <= bar.high:
        raise ValueError("bar close must lie within [low, high]")


def detect_liquidity_sweep(bar: Bar, reference_high: float, reference_low: float) -> Optional[Sweep]:
    """Detect a strict same-bar raid-and-close-back sweep.

    BSL: high trades above reference high and closes back below it.
    SSL: low trades below reference low and closes back above it.
    Ambiguous two-sided sweeps are rejected in v1.
    """
    _validate_bar(bar)
    if not (isfinite(reference_high) and isfinite(reference_low)):
        raise ValueError("reference levels must be finite")
    if reference_high <= reference_low:
        raise ValueError("reference_high must exceed reference_low")

    bsl = bar.high > reference_high and bar.close < reference_high
    ssl = bar.low < reference_low and bar.close > reference_low
    if bsl == ssl:
        return None
    if bsl:
        return Sweep("BSL", reference_high, bar.high - reference_high)
    return Sweep("SSL", reference_low, reference_low - bar.low)


def bullish_fvg(first: Bar, third: Bar) -> Optional[tuple[float, float]]:
    """Three-candle bullish FVG geometry: third.low > first.high."""
    _validate_bar(first)
    _validate_bar(third)
    if third.low > first.high:
        return first.high, third.low
    return None


def bearish_fvg(first: Bar, third: Bar) -> Optional[tuple[float, float]]:
    """Three-candle bearish FVG geometry: third.high < first.low."""
    _validate_bar(first)
    _validate_bar(third)
    if third.high < first.low:
        return third.high, first.low
    return None


def displacement_atr(bar: Bar, atr: float) -> float:
    """Absolute candle body normalized by point-in-time ATR."""
    _validate_bar(bar)
    if not isfinite(atr) or atr <= 0:
        raise ValueError("ATR must be finite and positive")
    return abs(bar.close - bar.open) / atr


def dealing_range_position(price: float, range_low: float, range_high: float) -> float:
    """0=discount extreme, 0.5=equilibrium, 1=premium extreme."""
    if not all(isfinite(v) for v in (price, range_low, range_high)):
        raise ValueError("dealing-range inputs must be finite")
    if range_high <= range_low:
        raise ValueError("range_high must exceed range_low")
    return (price - range_low) / (range_high - range_low)
