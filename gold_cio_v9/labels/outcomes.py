"""Outcome labels for Evidence Lab.

The labeler measures what happened after an independently generated candidate.
It does not create the candidate and therefore remains separate from alpha logic.
"""
from dataclasses import dataclass
from math import isfinite
from typing import Iterable


@dataclass(frozen=True)
class OutcomeLabel:
    mfe_r: float
    mae_r: float
    realized_r: float
    first_touch: str   # TARGET, STOP, AMBIGUOUS, NONE
    bars_to_first_touch: int | None


def _validate_geometry(*values: float) -> None:
    if not all(isfinite(v) for v in values):
        raise ValueError("entry/stop/target must be finite")


def _materialize_bars(future_bars: Iterable[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    bars = list(future_bars)
    for high, low, close in bars:
        if not all(isfinite(v) for v in (high, low, close)):
            raise ValueError("future bars must contain finite values")
        if high < low:
            raise ValueError("future bar high cannot be below low")
        if not low <= close <= high:
            raise ValueError("future bar close must lie within [low, high]")
    return bars


def _exit_index_long(
    bars: list[tuple[float, float, float]], stop: float, target: float
) -> tuple[str, int | None]:
    for idx, (high, low, _close) in enumerate(bars, start=1):
        hit_target = high >= target
        hit_stop = low <= stop
        if hit_target or hit_stop:
            if hit_target and hit_stop:
                return "AMBIGUOUS", idx
            return ("TARGET" if hit_target else "STOP"), idx
    return "NONE", None


def _exit_index_short(
    bars: list[tuple[float, float, float]], stop: float, target: float
) -> tuple[str, int | None]:
    for idx, (high, low, _close) in enumerate(bars, start=1):
        hit_target = low <= target
        hit_stop = high >= stop
        if hit_target or hit_stop:
            if hit_target and hit_stop:
                return "AMBIGUOUS", idx
            return ("TARGET" if hit_target else "STOP"), idx
    return "NONE", None


def label_long(entry: float, stop: float, target: float, future_bars: Iterable[tuple[float, float, float]]) -> OutcomeLabel:
    _validate_geometry(entry, stop, target)
    risk = entry - stop
    if risk <= 0 or target <= entry:
        raise ValueError("invalid long geometry")
    bars = _materialize_bars(future_bars)
    first_touch, touch_bar = _exit_index_long(bars, stop, target)

    # MFE/MAE are trade-path excursions, so observations after a deterministic
    # target/stop exit must not influence the label. For an ambiguous OHLC bar,
    # include that bar but never use subsequent bars.
    observed = bars[:touch_bar] if touch_bar is not None else bars
    max_high = max([entry] + [b[0] for b in observed])
    min_low = min([entry] + [b[1] for b in observed])
    last_close = bars[-1][2] if bars else entry

    mfe = (max_high - entry) / risk
    mae = (entry - min_low) / risk
    if first_touch == "TARGET":
        realized = (target - entry) / risk
    elif first_touch == "STOP":
        realized = -1.0
    elif first_touch == "AMBIGUOUS":
        realized = float("nan")
    else:
        realized = (last_close - entry) / risk
    return OutcomeLabel(mfe, mae, realized, first_touch, touch_bar)


def label_short(entry: float, stop: float, target: float, future_bars: Iterable[tuple[float, float, float]]) -> OutcomeLabel:
    _validate_geometry(entry, stop, target)
    risk = stop - entry
    if risk <= 0 or target >= entry:
        raise ValueError("invalid short geometry")
    bars = _materialize_bars(future_bars)
    first_touch, touch_bar = _exit_index_short(bars, stop, target)

    observed = bars[:touch_bar] if touch_bar is not None else bars
    max_high = max([entry] + [b[0] for b in observed])
    min_low = min([entry] + [b[1] for b in observed])
    last_close = bars[-1][2] if bars else entry

    mfe = (entry - min_low) / risk
    mae = (max_high - entry) / risk
    if first_touch == "TARGET":
        realized = (entry - target) / risk
    elif first_touch == "STOP":
        realized = -1.0
    elif first_touch == "AMBIGUOUS":
        realized = float("nan")
    else:
        realized = (entry - last_close) / risk
    return OutcomeLabel(mfe, mae, realized, first_touch, touch_bar)
