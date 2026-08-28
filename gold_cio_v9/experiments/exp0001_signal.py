"""Deterministic EXP-0001 signal state machine.

This module encodes the preregistered event order only:
HTF location -> liquidity sweep -> displacement/MSS -> FVG/IFVG retest -> entry.
It does not optimize thresholds, infer future structure, or repair missing events.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from gold_cio_v9.ict_engine.features import Bar, Sweep
from gold_cio_v9.ict_engine.structure import StructureEvent

Direction = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class TimedSweep:
    event_time: datetime
    sweep: Sweep


@dataclass(frozen=True)
class TimedStructure:
    event_time: datetime
    event: StructureEvent


@dataclass(frozen=True)
class FVGZone:
    event_time: datetime
    low: float
    high: float
    direction: Literal["BULLISH", "BEARISH"]
    kind: Literal["FVG", "IFVG"] = "FVG"

    def __post_init__(self) -> None:
        if self.high <= self.low:
            raise ValueError("FVG high must exceed low")


@dataclass(frozen=True)
class EXP0001Signal:
    direction: Direction
    entry_time: datetime
    entry_price: float
    swept_side: str
    swept_level: float
    fvg_low: float
    fvg_high: float
    fvg_kind: str


def _expected_direction(sweep: Sweep) -> Direction:
    if sweep.side == "SSL":
        return "LONG"
    if sweep.side == "BSL":
        return "SHORT"
    raise ValueError("sweep side must be SSL or BSL")


def _bar_retests_zone(bar: Bar, zone: FVGZone) -> bool:
    return bar.high >= zone.low and bar.low <= zone.high


def generate_exp0001_signal(
    *,
    htf_location_ok: bool,
    sweep: TimedSweep,
    structure: TimedStructure,
    zone: FVGZone,
    retest_time: datetime,
    retest_bar: Bar,
) -> EXP0001Signal | None:
    """Emit one EXP-0001 entry only when the locked event sequence is satisfied.

    The caller is responsible for point-in-time construction of HTF location,
    sweep, MSS and FVG/IFVG state. This function rejects wrong order/direction.
    Entry is the retest-bar close; execution costs are applied downstream by the
    backtest runner, not hidden here.
    """
    if not htf_location_ok:
        return None
    if not (sweep.event_time < structure.event_time <= zone.event_time < retest_time):
        return None
    if structure.event.kind != "MSS":
        return None

    direction = _expected_direction(sweep.sweep)
    if direction == "LONG":
        if structure.event.direction != "BULLISH" or zone.direction != "BULLISH":
            return None
    else:
        if structure.event.direction != "BEARISH" or zone.direction != "BEARISH":
            return None

    if not _bar_retests_zone(retest_bar, zone):
        return None

    return EXP0001Signal(
        direction=direction,
        entry_time=retest_time,
        entry_price=retest_bar.close,
        swept_side=sweep.sweep.side,
        swept_level=sweep.sweep.level,
        fvg_low=zone.low,
        fvg_high=zone.high,
        fvg_kind=zone.kind,
    )
