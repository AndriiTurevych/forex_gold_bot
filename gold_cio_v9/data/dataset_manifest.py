"""Deterministic manifesting for authoritative GC evidence datasets.

The manifest freezes dataset identity before statistical evidence is evaluated.
It records raw-contract coverage and a canonical SHA-256 over every authoritative
bar field used by the research pipeline. No price transformation occurs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from typing import Sequence

from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod


@dataclass(frozen=True)
class ContractCoverage:
    contract: str
    rows: int
    first_time: str
    last_time: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class DatasetManifest:
    instrument: str
    rows: int
    contracts: tuple[str, ...]
    coverage: tuple[ContractCoverage, ...]
    dataset_hash: str


def _canonical_row(b: HistoricalBar) -> dict[str, object]:
    return {
        "instrument": b.instrument,
        "contract": b.contract,
        "event_time": b.event_time.isoformat(),
        "open": b.open,
        "high": b.high,
        "low": b.low,
        "close": b.close,
        "volume": b.volume,
        "quality_state": b.quality_state.value,
        "source_id": b.source_id,
        "roll_method": b.roll_method.value,
        "is_roll_window": b.is_roll_window,
    }


def build_gc_dataset_manifest(bars: Sequence[HistoricalBar]) -> DatasetManifest:
    if not bars:
        raise ValueError("bars are required")
    if any(b.instrument != "GC" or not b.contract for b in bars):
        raise ValueError("manifest requires explicit GC contract identity")
    if any(b.roll_method is not RollMethod.RAW_CONTRACT for b in bars):
        raise ValueError("manifest accepts raw-contract GC bars only")
    if any(b.quality_state not in {QualityState.LIVE, QualityState.VERIFIED} for b in bars):
        raise ValueError("manifest accepts authoritative bars only")
    times = [b.event_time for b in bars]
    if any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError("bars must be strictly chronological with unique timestamps")

    contracts: list[str] = []
    seen_contracts: set[str] = set()
    for b in bars:
        assert b.contract is not None
        if b.contract not in seen_contracts:
            contracts.append(b.contract)
            seen_contracts.add(b.contract)
        elif contracts[-1] != b.contract:
            raise ValueError("contract identity cannot reappear after a later contract")

    coverage: list[ContractCoverage] = []
    for contract in contracts:
        rows = [b for b in bars if b.contract == contract]
        coverage.append(ContractCoverage(
            contract=contract,
            rows=len(rows),
            first_time=rows[0].event_time.isoformat(),
            last_time=rows[-1].event_time.isoformat(),
            source_ids=tuple(sorted({b.source_id for b in rows})),
        ))

    payload = dumps([_canonical_row(b) for b in bars], sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return DatasetManifest("GC", len(bars), tuple(contracts), tuple(coverage), digest)
