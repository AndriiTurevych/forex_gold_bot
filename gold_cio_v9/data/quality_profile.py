"""Deterministic quality profiling for normalized historical bars.

Profiles only observables present in the dataset. It does not interpolate missing
minutes or infer synthetic bars. Missing intervals are reported explicitly so the
evidence layer can decide whether coverage is sufficient.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

from gold_cio_v9.data.governance import HistoricalBar


@dataclass(frozen=True)
class DataQualityProfile:
    rows: int
    unique_timestamps: int
    duplicate_timestamps: int
    non_monotonic_timestamps: int
    gap_count: int
    max_gap_minutes: int
    zero_volume_rows: int
    negative_volume_rows: int

    @property
    def clean_identity(self) -> bool:
        return self.duplicate_timestamps == 0 and self.non_monotonic_timestamps == 0


def profile_minute_bars(bars: Sequence[HistoricalBar]) -> DataQualityProfile:
    if not bars:
        raise ValueError("bars are required")

    seen = set()
    duplicates = 0
    non_monotonic = 0
    gaps = 0
    max_gap = 0
    zero_volume = 0
    negative_volume = 0
    previous = None

    for b in bars:
        if b.event_time in seen:
            duplicates += 1
        seen.add(b.event_time)
        if previous is not None:
            delta = b.event_time - previous
            if delta <= timedelta(0):
                non_monotonic += 1
            elif delta > timedelta(minutes=1):
                gaps += 1
                gap_minutes = int(delta.total_seconds() // 60) - 1
                max_gap = max(max_gap, gap_minutes)
        previous = b.event_time
        if b.volume is not None:
            if b.volume == 0:
                zero_volume += 1
            elif b.volume < 0:
                negative_volume += 1

    return DataQualityProfile(
        rows=len(bars),
        unique_timestamps=len(seen),
        duplicate_timestamps=duplicates,
        non_monotonic_timestamps=non_monotonic,
        gap_count=gaps,
        max_gap_minutes=max_gap,
        zero_volume_rows=zero_volume,
        negative_volume_rows=negative_volume,
    )
