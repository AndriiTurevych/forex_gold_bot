"""Immutable lineage manifest for causal GC evidence acquisition."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from typing import Mapping, Sequence

from gold_cio_v9.data.causal_roll import MAX_SETTLEMENT_DAYS_FORWARD
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
    max_settlement_days_forward: int = MAX_SETTLEMENT_DAYS_FORWARD
    contract_master_hash: str = ""


def _canonical_lineage_payload(
    *,
    roll_buffer_days: int,
    roll_buffer_bars: int,
    max_settlement_days_forward: int,
    contract_master_hash: str,
    decisions: Sequence[RollDecisionLineage],
    fetch_windows: Sequence[tuple[str, str, str]],
    dataset_hash: str,
) -> dict[str, object]:
    if roll_buffer_days < 0 or roll_buffer_bars < 0:
        raise ValueError("roll buffers cannot be negative")
    if max_settlement_days_forward <= 0:
        raise ValueError("max_settlement_days_forward must be positive")
    if not isinstance(contract_master_hash, str):
        raise ValueError("contract_master_hash must be text")
    if not dataset_hash.strip():
        raise ValueError("dataset_hash is required")
    decision_rows = []
    previous_as_of = None
    for d in decisions:
        if not d.as_of or not d.liquidity_session_date or not d.selected_contract:
            raise ValueError("incomplete roll decision lineage")
        if previous_as_of is not None and d.as_of <= previous_as_of:
            raise ValueError("roll decisions must be strictly chronological")
        previous_as_of = d.as_of
        volumes = tuple(sorted((str(k), float(v)) for k, v in d.volume_by_contract))
        if len({k for k, _ in volumes}) != len(volumes):
            raise ValueError("duplicate contract volume in roll decision lineage")
        if any(v < 0 for _, v in volumes):
            raise ValueError("negative prior-session volume in lineage")
        if d.selected_contract not in {k for k, _ in volumes}:
            raise ValueError("selected contract missing from decision volume universe")
        decision_rows.append({
            "as_of": d.as_of,
            "liquidity_session_date": d.liquidity_session_date,
            "selected_contract": d.selected_contract,
            "volume_by_contract": [list(x) for x in volumes],
        })
    windows = [list(x) for x in fetch_windows]
    if any(len(x) != 3 or not all(str(v).strip() for v in x) for x in windows):
        raise ValueError("invalid fetch window lineage")
    return {
        "roll_buffer_days": roll_buffer_days,
        "roll_buffer_bars": roll_buffer_bars,
        "max_settlement_days_forward": max_settlement_days_forward,
        "contract_master_hash": contract_master_hash,
        "decisions": decision_rows,
        "fetch_windows": windows,
        "dataset_hash": dataset_hash,
    }


def compute_acquisition_lineage_hash(manifest: AcquisitionLineageManifest) -> str:
    payload = _canonical_lineage_payload(
        roll_buffer_days=manifest.roll_buffer_days,
        roll_buffer_bars=manifest.roll_buffer_bars,
        max_settlement_days_forward=manifest.max_settlement_days_forward,
        contract_master_hash=manifest.contract_master_hash,
        decisions=manifest.decisions,
        fetch_windows=manifest.fetch_windows,
        dataset_hash=manifest.dataset_hash,
    )
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def assert_acquisition_lineage_integrity(manifest: AcquisitionLineageManifest) -> None:
    if compute_acquisition_lineage_hash(manifest) != manifest.lineage_hash:
        raise ValueError("acquisition lineage hash mismatch")


def build_acquisition_lineage_manifest(
    *,
    requests: Sequence[LiquidityRequest],
    responses_by_as_of: Mapping,
    calendar: LiquidFrontCalendar,
    fetch_windows: Sequence[ContractFetchWindow],
    dataset_manifest: DatasetManifest,
    roll_buffer_days: int,
    roll_buffer_bars: int,
    max_settlement_days_forward: int = MAX_SETTLEMENT_DAYS_FORWARD,
    contract_master_hash: str = "",
) -> AcquisitionLineageManifest:
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
            request.as_of.isoformat(), request.session_date.isoformat(), day.contract, volumes,
        ))

    extra = set(responses_by_as_of) - {r.as_of for r in requests}
    if extra:
        raise ValueError("unexpected liquidity response lineage dates")

    windows = tuple((w.contract, w.start_date.isoformat(), w.end_date.isoformat()) for w in fetch_windows)
    provisional = AcquisitionLineageManifest(
        roll_buffer_days, roll_buffer_bars, tuple(decisions), windows,
        dataset_manifest.dataset_hash, "PENDING", max_settlement_days_forward,
        contract_master_hash,
    )
    lineage_hash = compute_acquisition_lineage_hash(provisional)
    manifest = AcquisitionLineageManifest(
        roll_buffer_days, roll_buffer_bars, tuple(decisions), windows,
        dataset_manifest.dataset_hash, lineage_hash, max_settlement_days_forward,
        contract_master_hash,
    )
    assert_acquisition_lineage_integrity(manifest)
    return manifest
