"""Causal context extraction for EXP-0001 research.

The functions in this module expose only information knowable at each bar close.
They do not choose strategy thresholds. Caller-supplied parameters are treated as
preregistered experiment inputs, not optimized inside this layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Sequence

from gold_cio_v9.data.governance import HistoricalBar
from gold_cio_v9.ict_engine.pit_events import ConfirmedSwing


@dataclass(frozen=True)
class CausalContext:
    index: int
    event_time: datetime
    atr_prior: float | None
    prior_day_high: float | None
    prior_day_low: float | None
    latest_swing_high: ConfirmedSwing | None
    latest_swing_low: ConfirmedSwing | None


def _validate_single_contract(bars: Sequence[HistoricalBar]) -> None:
    if not bars:
        raise ValueError("bars are required")
    contracts = {b.contract for b in bars}
    if len(contracts) != 1:
        raise ValueError("causal context must be built within one contract at a time")
    times = [b.event_time for b in bars]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("bars must be strictly chronological")
    if any(b.is_roll_window for b in bars):
        raise ValueError("roll-window bars are not allowed in causal context")


def confirm_swings(
    bars: Sequence[HistoricalBar],
    *,
    left_bars: int,
    right_bars: int,
) -> tuple[ConfirmedSwing, ...]:
    """Confirm strict local extrema only after right-side bars have closed."""
    _validate_single_contract(bars)
    if left_bars < 1 or right_bars < 1:
        raise ValueError("left_bars and right_bars must be positive")
    out: list[ConfirmedSwing] = []
    for i in range(left_bars, len(bars) - right_bars):
        center = bars[i]
        left = bars[i - left_bars : i]
        right = bars[i + 1 : i + 1 + right_bars]
        if all(center.high > b.high for b in (*left, *right)):
            out.append(ConfirmedSwing(
                "HIGH", center.high, center.event_time,
                bars[i + right_bars].event_time, left_bars, right_bars,
            ))
        if all(center.low < b.low for b in (*left, *right)):
            out.append(ConfirmedSwing(
                "LOW", center.low, center.event_time,
                bars[i + right_bars].event_time, left_bars, right_bars,
            ))
    return tuple(out)


def _true_range(current: HistoricalBar, previous_close: float) -> float:
    return max(
        current.high - current.low,
        abs(current.high - previous_close),
        abs(current.low - previous_close),
    )


def build_causal_context(
    bars: Sequence[HistoricalBar],
    *,
    atr_period: int,
    swing_left_bars: int,
    swing_right_bars: int,
) -> tuple[CausalContext, ...]:
    """Build point-in-time ATR, prior-day levels and confirmed swing state.

    ATR at index i uses only true ranges from bars strictly before i. Previous-day
    high/low are published only after the UTC calendar day has completed. Swing
    state includes only extrema whose available_time <= current bar event_time.
    """
    _validate_single_contract(bars)
    if atr_period < 1:
        raise ValueError("atr_period must be positive")
    swings = confirm_swings(bars, left_bars=swing_left_bars, right_bars=swing_right_bars)

    true_ranges: list[float] = []
    day_levels: dict[object, tuple[float, float]] = {}
    by_day: dict[object, list[HistoricalBar]] = {}
    for b in bars:
        by_day.setdefault(b.event_time.date(), []).append(b)
    for day, rows in by_day.items():
        day_levels[day] = (max(r.high for r in rows), min(r.low for r in rows))

    days = sorted(day_levels)
    previous_day: dict[object, tuple[float, float]] = {
        days[i]: day_levels[days[i - 1]] for i in range(1, len(days))
    }

    out: list[CausalContext] = []
    for i, b in enumerate(bars):
        atr = None
        if i >= 1:
            tr = _true_range(bars[i - 1], bars[i - 2].close) if i >= 2 else bars[0].high - bars[0].low
            if not isfinite(tr) or tr < 0:
                raise ValueError("invalid true range")
            true_ranges.append(tr)
        if len(true_ranges) >= atr_period:
            atr = sum(true_ranges[-atr_period:]) / atr_period
            if atr <= 0:
                raise ValueError("ATR must be positive")

        visible = [s for s in swings if s.available_time <= b.event_time]
        high = max((s for s in visible if s.kind == "HIGH"), key=lambda s: s.available_time, default=None)
        low = max((s for s in visible if s.kind == "LOW"), key=lambda s: s.available_time, default=None)
        pd = previous_day.get(b.event_time.date())
        out.append(CausalContext(
            i, b.event_time, atr,
            pd[0] if pd else None,
            pd[1] if pd else None,
            high, low,
        ))
    return tuple(out)
