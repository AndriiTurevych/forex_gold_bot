"""Historical market-data governance for Gold CIO v9.

EXP-0001 is preregistered on GC. Research datasets must preserve contract identity,
roll metadata and point-in-time quality state. Continuous adjusted series may be
used for secondary analytics, but signal generation must be traceable to raw
contract-level observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Literal


class QualityState(str, Enum):
    LIVE = "LIVE"
    VERIFIED = "VERIFIED"
    STALE = "STALE"
    PROXY = "PROXY"
    BAD = "BAD"


class RollMethod(str, Enum):
    RAW_CONTRACT = "RAW_CONTRACT"
    DIFFERENCE_ADJUSTED = "DIFFERENCE_ADJUSTED"
    RATIO_ADJUSTED = "RATIO_ADJUSTED"


@dataclass(frozen=True)
class HistoricalBar:
    instrument: Literal["GC", "XAUUSD"]
    contract: str | None
    event_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    quality_state: QualityState
    source_id: str
    roll_method: RollMethod
    is_roll_window: bool = False

    def __post_init__(self) -> None:
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware")
        vals = (self.open, self.high, self.low, self.close)
        if not all(isfinite(v) for v in vals):
            raise ValueError("OHLC must be finite")
        if self.high < self.low or not self.low <= self.open <= self.high or not self.low <= self.close <= self.high:
            raise ValueError("invalid OHLC geometry")
        if self.instrument == "GC" and not self.contract:
            raise ValueError("GC research bars require explicit contract identity")
        if self.instrument == "XAUUSD" and self.contract is not None:
            raise ValueError("XAUUSD bars must not carry futures contract identity")
        if not self.source_id.strip():
            raise ValueError("source_id is required")


def eligible_for_signal_generation(bar: HistoricalBar) -> bool:
    """Fail closed for stale/proxy/bad bars and roll windows."""
    if bar.quality_state not in {QualityState.LIVE, QualityState.VERIFIED}:
        return False
    if bar.instrument == "GC" and bar.roll_method is not RollMethod.RAW_CONTRACT:
        return False
    if bar.is_roll_window:
        return False
    return True


def require_dataset_ready(bars: list[HistoricalBar], *, instrument: str) -> None:
    """Validate a dataset before it may enter an evidence run."""
    if not bars:
        raise ValueError("dataset is empty")
    if any(b.instrument != instrument for b in bars):
        raise ValueError("mixed instruments are not allowed in a single evidence dataset")
    if instrument == "GC" and any(b.roll_method is not RollMethod.RAW_CONTRACT for b in bars):
        raise ValueError("GC evidence runs require raw contract-level bars; adjusted continuous prices are not authoritative")
    if any(b.quality_state in {QualityState.STALE, QualityState.PROXY, QualityState.BAD} for b in bars):
        raise ValueError("dataset contains non-authoritative quality_state rows")
    if any(b.is_roll_window for b in bars):
        raise ValueError("roll-window bars must be excluded from signal-generation evidence datasets")
