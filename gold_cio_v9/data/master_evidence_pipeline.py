"""One-call data-only acquisition assembly for EXP-0001 Baseline Policy V5.

The caller supplies an immutable GC contract master, requested evidence dates,
explicit prior completed-session dates, completed per-contract volume responses and
complete raw 1-minute aggregate pages. This module performs no network I/O and no
strategy outcome calculation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

from gold_cio_v9.data.contract_master import ContractMaster
from gold_cio_v9.data.evidence_dataset_pipeline import EvidenceDatasetResult, assemble_evidence_dataset
from gold_cio_v9.data.evidence_lineage import AcquisitionLineageManifest, build_acquisition_lineage_manifest
from gold_cio_v9.data.master_front_calendar import MasterLiquidityRequest, build_master_liquid_front_calendar, build_master_liquidity_request_plan
from gold_cio_v9.experiments.exp0001_locked import MAX_SETTLEMENT_DAYS_FORWARD, ROLL_BUFFER_BARS, ROLL_BUFFER_DAYS


@dataclass(frozen=True)
class MasterEvidenceResult:
    requests: tuple[MasterLiquidityRequest, ...]
    dataset: EvidenceDatasetResult
    lineage: AcquisitionLineageManifest


def build_master_evidence_dataset(
    *,
    master: ContractMaster,
    dates: Sequence[date],
    prior_session_date_by_as_of: Mapping[date, date],
    liquidity_responses_by_as_of: Mapping[date, Mapping[str, Sequence[Mapping[str, object]]]],
    pages_by_contract: Mapping[str, Sequence[Mapping[str, Any]]],
) -> MasterEvidenceResult:
    """Build a fully identity-bound raw-contract dataset under locked V5 policy."""
    if not master.master_hash.strip():
        raise ValueError("immutable contract master hash is required")
    requests = build_master_liquidity_request_plan(
        master, dates=dates, prior_session_date_by_as_of=prior_session_date_by_as_of,
        roll_buffer_days=ROLL_BUFFER_DAYS,
        max_settlement_days_forward=MAX_SETTLEMENT_DAYS_FORWARD,
    )
    calendar = build_master_liquid_front_calendar(
        master, requests=requests, responses_by_as_of=liquidity_responses_by_as_of,
        roll_buffer_days=ROLL_BUFFER_DAYS,
        max_settlement_days_forward=MAX_SETTLEMENT_DAYS_FORWARD,
    )
    dataset = assemble_evidence_dataset(
        calendar, pages_by_contract=pages_by_contract, roll_buffer_bars=ROLL_BUFFER_BARS,
    )
    lineage = build_acquisition_lineage_manifest(
        requests=requests,
        responses_by_as_of=liquidity_responses_by_as_of,
        calendar=calendar,
        fetch_windows=dataset.fetch_windows,
        dataset_manifest=dataset.manifest,
        roll_buffer_days=ROLL_BUFFER_DAYS,
        roll_buffer_bars=ROLL_BUFFER_BARS,
        max_settlement_days_forward=MAX_SETTLEMENT_DAYS_FORWARD,
        contract_master_hash=master.master_hash,
    )
    if lineage.contract_master_hash != master.master_hash:
        raise RuntimeError("lineage failed to bind immutable contract master")
    if lineage.dataset_hash != dataset.manifest.dataset_hash:
        raise RuntimeError("lineage failed to bind evidence dataset")
    return MasterEvidenceResult(requests, dataset, lineage)
