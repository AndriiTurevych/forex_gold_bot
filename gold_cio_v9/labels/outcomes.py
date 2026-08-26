"""Outcome labels for Evidence Lab.

The labeler measures what happened after an independently generated candidate.
It does not create the candidate and therefore can be kept separate from alpha logic.
"""
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class OutcomeLabel:
    mfe_r: float
    mae_r: float
    realized_r: float
    first_touch: str   # TARGET, STOP, NONE
    bars_to_first_touch: int | None


def label_long(entry: float, stop: float, target: float, future_bars: Iterable[tuple[float, float, float]]) -> OutcomeLabel:
    risk = entry - stop
    if risk <= 0 or target <= entry:
        raise ValueError("invalid long geometry")
    max_high = entry
    min_low = entry
    first_touch = "NONE"
    touch_bar = None
    last_close = entry
    for idx, (high, low, close) in enumerate(future_bars, start=1):
        max_high = max(max_high, high)
        min_low = min(min_low, low)
        last_close = close
        hit_target = high >= target
        hit_stop = low <= stop
        if first_touch == "NONE" and (hit_target or hit_stop):
            if hit_target and hit_stop:
                first_touch = "NONE"  # ambiguous intrabar ordering in bar data
            else:
                first_touch = "TARGET" if hit_target else "STOP"
            touch_bar = idx
            if first_touch != "NONE":
                break
    mfe = (max_high - entry) / risk
    mae = (entry - min_low) / risk
    if first_touch == "TARGET":
        realized = (target - entry) / risk
    elif first_touch == "STOP":
        realized = -1.0
    else:
        realized = (last_close - entry) / risk
    return OutcomeLabel(mfe, mae, realized, first_touch, touch_bar)


def label_short(entry: float, stop: float, target: float, future_bars: Iterable[tuple[float, float, float]]) -> OutcomeLabel:
    risk = stop - entry
    if risk <= 0 or target >= entry:
        raise ValueError("invalid short geometry")
    max_high = entry
    min_low = entry
    first_touch = "NONE"
    touch_bar = None
    last_close = entry
    for idx, (high, low, close) in enumerate(future_bars, start=1):
        max_high = max(max_high, high)
        min_low = min(min_low, low)
        last_close = close
        hit_target = low <= target
        hit_stop = high >= stop
        if first_touch == "NONE" and (hit_target or hit_stop):
            if hit_target and hit_stop:
                first_touch = "NONE"
            else:
                first_touch = "TARGET" if hit_target else "STOP"
            touch_bar = idx
            if first_touch != "NONE":
                break
    mfe = (entry - min_low) / risk
    mae = (max_high - entry) / risk
    if first_touch == "TARGET":
        realized = (entry - target) / risk
    elif first_touch == "STOP":
        realized = -1.0
    else:
        realized = (entry - last_close) / risk
    return OutcomeLabel(mfe, mae, realized, first_touch, touch_bar)
