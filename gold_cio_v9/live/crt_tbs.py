"""Deterministic CRT + TBS signal engine for MIDAS v2.

CRT defines a fully closed higher-timeframe candle range. TBS is a lower-timeframe
failed breakout: price sweeps one boundary and closes back inside the CRT range.
Only closed candles are consumed; one range/side maps to one stable signal_id.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from typing import Any


@dataclass(frozen=True)
class CRTTBSSetup:
    signal_id: str
    model: str
    direction: str
    range_time: str
    range_high: float
    range_low: float
    range_mid: float
    trigger_time: str
    trigger_open: float
    trigger_high: float
    trigger_low: float
    trigger_close: float
    swept_side: str
    sweep_depth: float
    sweep_depth_fraction: float
    body_fraction: float
    atr: float
    entry: float
    stop: float
    tp1: float
    tp2: float
    rr_tp1: float
    rr_tp2: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _signal_id(model: str, range_time: str, swept_side: str) -> str:
    raw = f"{model}|{range_time}|{swept_side}".encode("utf-8")
    return "CRT-" + sha256(raw).hexdigest()[:20]


def _atr(bars: list[Any], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(len(bars) - period, len(bars)):
        current = bars[i]
        previous = bars[i - 1]
        trs.append(max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        ))
    value = sum(trs) / period
    return value if value > 0 else None


def _candidate(
    *,
    model: str,
    reference: Any,
    trigger: Any,
    atr: float,
    min_sweep_fraction: float,
    max_sweep_fraction: float,
    min_body_fraction: float,
    min_rr_tp2: float,
) -> CRTTBSSetup | None:
    range_high = float(reference.high)
    range_low = float(reference.low)
    width = range_high - range_low
    if width <= 0 or atr <= 0:
        return None

    body_fraction = abs(trigger.close - trigger.open) / max(trigger.high - trigger.low, 1e-12)
    if body_fraction < min_body_fraction:
        return None

    long_sweep = (
        trigger.low < range_low
        and range_low < trigger.close < range_high
        and trigger.close > trigger.open
    )
    short_sweep = (
        trigger.high > range_high
        and range_low < trigger.close < range_high
        and trigger.close < trigger.open
    )
    if long_sweep == short_sweep:
        return None

    if long_sweep:
        direction = "LONG"
        swept_side = "LOW"
        sweep_depth = range_low - trigger.low
        stop = trigger.low - 0.10 * atr
        entry = trigger.close
        tp2 = range_high
        midpoint = (range_high + range_low) / 2
        risk = entry - stop
        if risk <= 0 or tp2 <= entry:
            return None
        tp1 = midpoint if midpoint > entry else entry + risk
        if tp1 >= tp2:
            tp1 = entry + 0.5 * (tp2 - entry)
    else:
        direction = "SHORT"
        swept_side = "HIGH"
        sweep_depth = trigger.high - range_high
        stop = trigger.high + 0.10 * atr
        entry = trigger.close
        tp2 = range_low
        midpoint = (range_high + range_low) / 2
        risk = stop - entry
        if risk <= 0 or tp2 >= entry:
            return None
        tp1 = midpoint if midpoint < entry else entry - risk
        if tp1 <= tp2:
            tp1 = entry - 0.5 * (entry - tp2)

    depth_fraction = sweep_depth / width
    if not min_sweep_fraction <= depth_fraction <= max_sweep_fraction:
        return None

    reward1 = abs(tp1 - entry)
    reward2 = abs(tp2 - entry)
    rr1 = reward1 / risk
    rr2 = reward2 / risk
    if rr2 < min_rr_tp2:
        return None

    return CRTTBSSetup(
        signal_id=_signal_id(model, reference.time.isoformat(), swept_side),
        model=model,
        direction=direction,
        range_time=reference.time.isoformat(),
        range_high=round(range_high, 5),
        range_low=round(range_low, 5),
        range_mid=round((range_high + range_low) / 2, 5),
        trigger_time=trigger.time.isoformat(),
        trigger_open=round(trigger.open, 5),
        trigger_high=round(trigger.high, 5),
        trigger_low=round(trigger.low, 5),
        trigger_close=round(trigger.close, 5),
        swept_side=swept_side,
        sweep_depth=round(sweep_depth, 5),
        sweep_depth_fraction=round(depth_fraction, 6),
        body_fraction=round(body_fraction, 6),
        atr=round(atr, 5),
        entry=round(entry, 5),
        stop=round(stop, 5),
        tp1=round(tp1, 5),
        tp2=round(tp2, 5),
        rr_tp1=round(rr1, 4),
        rr_tp2=round(rr2, 4),
    )


def detect_crt_tbs(
    *,
    h4: list[Any],
    h1: list[Any],
    m15: list[Any],
    m5: list[Any],
    min_sweep_fraction: float = 0.02,
    max_sweep_fraction: float = 0.33,
    min_body_fraction: float = 0.30,
    min_rr_tp2: float = 1.80,
    max_trigger_age_bars: int = 2,
) -> CRTTBSSetup | None:
    """Find the freshest valid setup across H1->M5 and H4->M15 models."""
    found: list[tuple[Any, CRTTBSSetup]] = []

    def scan(model: str, refs: list[Any], triggers: list[Any]) -> None:
        if len(refs) < 2 or len(triggers) < 16:
            return
        # The latest fully closed HTF candle is the current CRT range.
        reference = refs[-1]
        reference_close = reference.time + (h4[1].time - h4[0].time if model == "H4_M15" and len(h4) > 1 else h1[1].time - h1[0].time)
        eligible = [bar for bar in triggers if bar.time >= reference_close]
        if not eligible:
            return
        atr = _atr(triggers)
        if atr is None:
            return
        for idx, trigger in enumerate(eligible):
            setup = _candidate(
                model=model,
                reference=reference,
                trigger=trigger,
                atr=atr,
                min_sweep_fraction=min_sweep_fraction,
                max_sweep_fraction=max_sweep_fraction,
                min_body_fraction=min_body_fraction,
                min_rr_tp2=min_rr_tp2,
            )
            if setup is None:
                continue
            age = len(eligible) - 1 - idx
            if age <= max_trigger_age_bars:
                found.append((trigger.time, setup))

    scan("H4_M15", h4, m15)
    scan("H1_M5", h1, m5)
    if not found:
        return None
    found.sort(key=lambda row: row[0])
    return found[-1][1]
