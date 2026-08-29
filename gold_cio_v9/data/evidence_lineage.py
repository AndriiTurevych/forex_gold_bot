"""Immutable lineage manifest for causal GC evidence acquisition.

The bar-level DatasetManifest proves what prices entered research. This companion
manifest proves *why those contracts were selected*: exact PIT decision dates,
completed liquidity-session dates, competitor volumes, selected front contracts,
fetch windows, roll policy parameters, and the downstream dataset hash.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from typing import Mapping, Sequence

from gold_cio_v9.data.dataset_manifest import DatasetManifest
from gold_cio_v9.data.evidence_dataset_pipeline import LiquidityRequest
from gold_cio_v9.data.liquid_front_calendar import LiquidFrontCalendar
from gold_cio_v9.data.massive_fetch_plan import ContractFetchWindow
from gold_cio_v9.data.prior_session_liquidity import build_prior_session_liquidity


@dataclass(frozen=True)
class RollDecisionLineage:
    as_of: str
    liquidity_session_date: str
    selected_contract: str
    volume_by_contract: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class AcquisitionLineageManifest:
    roll_buffer_days: int
    roll_buffer_bars: int
    decisions: tuple[RollDecisionLineage, ...]
    fetch_windows: tuple[tuple[str, str, str], ...]
    dataset_hash: str
    lineage_hash: str


def build_acquisition_lineage_manifest(
    *,
    requests: Sequence[LiquidityRequest],
    responses_by_as_of: Mapping,
    calendar: LiquidFrontCalendar,
    fetch_windows: Sequence[ContractFetchWindow],
    dataset_manifest: DatasetManifest,
    roll_buffer_days: int,
    roll_buffer_bars: int,
) -> AcquisitionLineageManifest:
    if roll_buffer_days < 0 or roll_buffer_bars < 0:
        raise ValueError("roll buffers cannot be negative")
    if not requests or not calendar.days or not fetch_windows:
        raise ValueError("complete acquisition lineage inputs are required")
    if len(requests) != len(calendar.days):
        raise ValueError("request/calendar length mismatch")
    if tuple(w.contract for w in fetch_windows) != calendar.contract_order:
        raise ValueError("fetch windows diverge from calendar contract order")
    if dataset_manifest.contracts != calendar.contract_order:
        raise ValueError("dataset manifest diverges from calendar contract order")

    decisions = []
    for request, day in zip(requests, calendar.days):
        if request.as_of != day.as_of:
            raise ValueError("request/calendar date mismatch")
        if request.session_date != day.liquidity_session_date:
            raise ValueError("liquidity session lineage mismatch")
        if day.contract not in request.contracts:
            raise ValueError("selected contract absent from request universe")
        responses = responses_by_as_of.get(request.as_of)
        if responses is None:
            raise ValueError("missing liquidity response lineage")
        snapshot = build_prior_session_liquidity(
            responses,
            expected_contracts=request.contracts,
            session_date=request.session_date,
        )
        volumes = tuple(sorted((k, float(v)) for k, v in snapshot.volume_by_contract.items()))
        decisions.append(RollDecisionLineage(
            request.as_of.isoformat(),
            request.session_date.isoformat(),
            day.contract,
            volumes,
        ))

    extra = set(responses_by_as_of) - {r.as_of for r in requests}
    if extra:
        raise ValueError("unexpected liquidity response lineage dates")

    windows = tuple((w.contract, w.start_date.isoformat(), w.end_date.isoformat()) for w in fetch_windows)
    canonical = {
        "roll_buffer_days": roll_buffer_days,
        "roll_buffer_bars": roll_buffer_bars,
        "decisions": [
            {
                "as_of": d.as_of,
                "liquidity_session_date": d.liquidity_session_date,
                "selected_contract": d.selected_contract,
                "volume_by_contract": list(d.volume_by_contract),
            }
            for d in decisions
        ],
        "fetch_windows": list(windows),
        "dataset_hash": dataset_manifest.dataset_hash,
    }
    payload = dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)
    lineage_hash = sha256(payload.encode("utf-8")).hexdigest()
    return AcquisitionLineageManifest(
        roll_buffer_days,
        roll_buffer_bars,
        tuple(decisions),
        windows,
        dataset_manifest.dataset_hash,
        lineage_hash,
    )
