"""Massive futures aggregate adapter for authoritative GC evidence data.

The adapter is intentionally narrow: it converts contract-level Massive aggregate
rows into HistoricalBar objects without interpolation, back-adjustment, or ticker
splicing. Missing intervals remain missing and must be handled by data-quality
checks upstream. This preserves absolute ICT price levels and contract identity.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Iterable, Mapping, Any

from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod


SOURCE_ID = "massive:futures:v1:aggs"


def _utc_from_ns(value: Any) -> datetime:
    try:
        ns = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("window_start must be an integer nanosecond timestamp") from exc
    if ns <= 0:
        raise ValueError("window_start must be positive")
    return datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc)


def _number(row: Mapping[str, Any], key: str) -> float:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"missing/invalid {key}") from exc
    if not isfinite(value):
        raise ValueError(f"{key} must be finite")
    return value


def parse_massive_gc_aggs(rows: Iterable[Mapping[str, Any]]) -> list[HistoricalBar]:
    """Normalize Massive contract-level aggregate rows into verified GC bars.

    Rules are fail-closed:
    - only single GC contract tickers are accepted; spread/combo tickers are rejected;
    - timestamps must be unique;
    - records are sorted by event time;
    - no missing bars are synthesized;
    - no continuous-series adjustment is performed.
    """
    bars: list[HistoricalBar] = []
    seen: set[tuple[str, datetime]] = set()

    for row in rows:
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker.startswith("GC") or "-" in ticker:
            raise ValueError(f"invalid GC single-contract ticker: {ticker!r}")

        event_time = _utc_from_ns(row.get("window_start"))
        identity = (ticker, event_time)
        if identity in seen:
            raise ValueError(f"duplicate aggregate bar: {ticker} {event_time.isoformat()}")
        seen.add(identity)

        volume_raw = row.get("volume")
        volume = None if volume_raw is None else float(volume_raw)
        if volume is not None and (not isfinite(volume) or volume < 0):
            raise ValueError("volume must be finite and non-negative")

        bars.append(
            HistoricalBar(
                instrument="GC",
                contract=ticker,
                event_time=event_time,
                open=_number(row, "open"),
                high=_number(row, "high"),
                low=_number(row, "low"),
                close=_number(row, "close"),
                volume=volume,
                quality_state=QualityState.VERIFIED,
                source_id=SOURCE_ID,
                roll_method=RollMethod.RAW_CONTRACT,
                is_roll_window=False,
            )
        )

    if not bars:
        raise ValueError("Massive aggregate response is empty")

    bars.sort(key=lambda b: (b.event_time, b.contract or ""))
    return bars
