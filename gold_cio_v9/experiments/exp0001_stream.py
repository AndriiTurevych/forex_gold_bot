"""Causal event-stream construction for EXP-0001.

Consumes raw, chronological GC bars plus point-in-time reference context and emits
candidate sweep/MSS/FVG events without future leakage. This layer does not tune
thresholds, choose outcomes or create trades; it only creates time-ordered events.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from gold_cio_v9.data.governance import HistoricalBar, eligible_for_signal_generation
from gold_cio_v9.experiments.exp0001_events import TimedBar, extract_fvg, extract_mss, extract_sweep
from gold_cio_v9.experiments.exp0001_signal import FVGZone, TimedStructure, TimedSweep
from gold_cio_v9.ict_engine.features import Bar


@dataclass(frozen=True)
class ContextPoint:
    index: int
    reference_high: float
    reference_low: float
    prior_swing_high: float
    prior_swing_low: float
    prior_trend: str
    atr: float


@dataclass(frozen=True)
class StreamEvent:
    index: int
    sweep: TimedSweep | None
    structure: TimedStructure | None
    bullish_fvg: FVGZone | None
    bearish_fvg: FVGZone | None


def _to_timed_bar(h: HistoricalBar) -> TimedBar:
    return TimedBar(
        h.event_time,
        Bar(
            ts=h.event_time.isoformat(),
            open=h.open,
            high=h.high,
            low=h.low,
            close=h.close,
        ),
    )


def build_event_stream(
    bars: Sequence[HistoricalBar],
    context: Sequence[ContextPoint],
) -> tuple[StreamEvent, ...]:
    """Build causal EXP-0001 primitives for bars with available context.

    Invariants:
    - bar timestamps strictly increase;
    - context indices strictly increase and refer only to existing bars;
    - no event is emitted from roll-window or otherwise ineligible bars;
    - FVG at index i is confirmed using i-2, i-1, i only, therefore available at i.
    """
    if not bars:
        raise ValueError("bars are required")
    times = [b.event_time for b in bars]
    if any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError("bar timestamps must be strictly increasing")
    indices = [c.index for c in context]
    if any(i < 0 or i >= len(bars) for i in indices):
        raise ValueError("context index out of range")
    if any(a >= b for a, b in zip(indices, indices[1:])):
        raise ValueError("context indices must be strictly increasing")

    ctx = {c.index: c for c in context}
    timed = [_to_timed_bar(b) for b in bars]
    events: list[StreamEvent] = []

    for i, current in enumerate(timed):
        c = ctx.get(i)
        if c is None or not eligible_for_signal_generation(bars[i]):
            continue
        sweep = extract_sweep(
            current,
            reference_high=c.reference_high,
            reference_low=c.reference_low,
        )
        structure = extract_mss(
            current,
            prior_swing_high=c.prior_swing_high,
            prior_swing_low=c.prior_swing_low,
            prior_trend=c.prior_trend,
            atr=c.atr,
        )
        bull = bear = None
        if i >= 2 and all(eligible_for_signal_generation(bars[j]) for j in (i - 2, i - 1, i)):
            bull = extract_fvg(timed[i - 2], timed[i - 1], current, direction="BULLISH")
            bear = extract_fvg(timed[i - 2], timed[i - 1], current, direction="BEARISH")
        events.append(StreamEvent(i, sweep, structure, bull, bear))

    return tuple(events)
