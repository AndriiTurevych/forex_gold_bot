"""Deterministic assembly of raw-contract GC evidence datasets.

This layer stitches already-normalized contract bars without changing prices.
It deliberately does not create a continuous adjusted series. Contract boundaries
remain explicit and are marked as roll windows so signal-generation evidence
cannot accidentally cross them.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Mapping, Sequence

from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod


def assemble_gc_dataset(
    contract_bars: Mapping[str, Sequence[HistoricalBar]],
    *,
    contract_order: Sequence[str],
    roll_buffer_bars: int = 1,
) -> tuple[HistoricalBar, ...]:
    """Assemble raw GC contracts in predeclared order and mark boundaries.

    No price adjustment, interpolation, contract selection or volume/OI hindsight
    occurs here. The caller supplies the precommitted contract order.
    """
    if roll_buffer_bars < 0:
        raise ValueError("roll_buffer_bars cannot be negative")
    if not contract_order:
        raise ValueError("contract_order is required")
    if len(set(contract_order)) != len(contract_order):
        raise ValueError("contract_order contains duplicates")

    out: list[HistoricalBar] = []
    previous_time: datetime | None = None
    previous_contract: str | None = None

    for contract in contract_order:
        rows = list(contract_bars.get(contract, ()))
        if not rows:
            raise ValueError(f"missing bars for contract {contract}")
        rows.sort(key=lambda b: b.event_time)
        if len({b.event_time for b in rows}) != len(rows):
            raise ValueError(f"duplicate timestamps in contract {contract}")
        for b in rows:
            if b.instrument != "GC" or b.contract != contract:
                raise ValueError(f"contract identity mismatch for {contract}")
            if b.roll_method is not RollMethod.RAW_CONTRACT:
                raise ValueError("adjusted GC prices are not allowed")
            if b.quality_state not in {QualityState.LIVE, QualityState.VERIFIED}:
                raise ValueError("non-authoritative bars are not allowed")
        if previous_time is not None and rows[0].event_time <= previous_time:
            raise ValueError("contract windows overlap or are not chronological")

        boundary = previous_contract is not None
        n = len(rows)
        for i, b in enumerate(rows):
            mark = b.is_roll_window or (boundary and i < roll_buffer_bars)
            out.append(replace(b, is_roll_window=mark))
        previous_time = rows[-1].event_time
        previous_contract = contract

    return tuple(out)
