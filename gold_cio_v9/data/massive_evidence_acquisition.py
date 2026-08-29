"""Reproducible external acquisition engine for EXP-0001 formal GC evidence.

This module contains no strategy logic. It reconstructs the locked causal futures
chain from an immutable contract master and completed prior-session volume, then
fetches the exact raw 1-minute sessions assigned to that chain. All selection occurs
before strategy outcomes and uses only data available before each session.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from gold_cio_v9.data.contract_master import ContractMaster
from gold_cio_v9.data.evidence_lineage import AcquisitionLineageManifest
from gold_cio_v9.data.master_evidence_pipeline import MasterEvidenceResult, build_master_evidence_dataset
from gold_cio_v9.data.master_front_calendar import build_master_liquidity_request_plan
from gold_cio_v9.experiments.exp0001_locked import (
    MAX_SETTLEMENT_DAYS_FORWARD,
    ROLL_BUFFER_DAYS,
)

JsonGet = Callable[[str, Mapping[str, object]], Mapping[str, Any]]


def _validate_page(page: Mapping[str, Any]) -> None:
    if page.get("status") not in (None, "OK"):
        raise ValueError(f"Massive response status is not OK: {page.get('status')!r}")
    results = page.get("results")
    if results is None:
        raise ValueError("Massive response is missing results")
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise ValueError("Massive results must be a sequence")


def fetch_all_pages(
    get_json: JsonGet,
    *,
    path: str,
    params: Mapping[str, object],
    max_pages: int = 100,
) -> tuple[Mapping[str, Any], ...]:
    """Fetch a complete Massive cursor chain using an injected transport.

    The transport receives either the original endpoint path or a ``next_url`` and
    a parameter mapping. For a next_url the mapping is empty because Massive embeds
    its cursor in that URL. Repeated next URLs and runaway pagination fail closed.
    """
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    pages: list[Mapping[str, Any]] = []
    target = path
    query: Mapping[str, object] = dict(params)
    seen_next: set[str] = set()
    for _ in range(max_pages):
        page = get_json(target, query)
        if not isinstance(page, Mapping):
            raise ValueError("Massive transport must return an object")
        _validate_page(page)
        pages.append(page)
        next_url = page.get("next_url")
        if not next_url:
            return tuple(pages)
        nxt = str(next_url)
        if nxt in seen_next:
            raise ValueError("Massive pagination repeated next_url")
        seen_next.add(nxt)
        target, query = nxt, {}
    raise ValueError("Massive pagination exceeded max_pages")


def _session_history_rows(
    pages: Sequence[Mapping[str, Any]], *, expected_contract: str,
) -> dict[date, Mapping[str, object]]:
    """Return at most one completed 1session row per trading date."""
    out: dict[date, Mapping[str, object]] = {}
    request_ids: set[str] = set()
    for i, page in enumerate(pages):
        _validate_page(page)
        if i < len(pages) - 1 and not page.get("next_url"):
            raise ValueError("session pagination terminated early")
        if i == len(pages) - 1 and page.get("next_url"):
            raise ValueError("session pagination is incomplete")
        rid = page.get("request_id")
        if rid is not None:
            value = str(rid)
            if value in request_ids:
                raise ValueError("duplicate session request_id")
            request_ids.add(value)
        for row0 in page.get("results", ()):
            if not isinstance(row0, Mapping):
                raise ValueError("session aggregate row must be an object")
            if str(row0.get("ticker", "")) != expected_contract:
                raise ValueError("session aggregate ticker mismatch")
            raw_date = row0.get("session_end_date")
            if not isinstance(raw_date, str):
                raise ValueError("session aggregate is missing session_end_date")
            session_date = date.fromisoformat(raw_date)
            if session_date in out:
                raise ValueError("duplicate 1session aggregate for contract/date")
            raw_volume = row0.get("volume")
            try:
                volume = float(raw_volume)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid session volume") from exc
            if volume < 0:
                raise ValueError("negative session volume")
            out[session_date] = dict(row0)
    return out


def acquire_session_histories(
    get_json: JsonGet,
    *,
    master: ContractMaster,
    coverage_start: date,
    coverage_end: date,
    lookback_days: int = 10,
) -> Mapping[str, Mapping[date, Mapping[str, object]]]:
    """Acquire complete per-contract session bars used only for causal roll choice."""
    if coverage_end < coverage_start:
        raise ValueError("coverage_end precedes coverage_start")
    if lookback_days < 2:
        raise ValueError("lookback_days must be at least two")
    lower = coverage_start - timedelta(days=lookback_days + 1)
    upper = coverage_end
    histories: dict[str, Mapping[date, Mapping[str, object]]] = {}
    for spec in master.specs:
        if spec.last_trade_date < lower or spec.first_trade_date > coverage_end:
            continue
        pages = fetch_all_pages(
            get_json,
            path=f"/futures/v1/aggs/{spec.ticker}",
            params={
                "resolution": "1session",
                "window_start.gte": (lower - timedelta(days=1)).isoformat(),
                "window_start.lte": upper.isoformat(),
                "sort": "window_start.asc",
                "limit": 50000,
            },
        )
        histories[spec.ticker] = _session_history_rows(pages, expected_contract=spec.ticker)
    if not histories:
        raise ValueError("no GC session histories were acquired")
    return histories


def derive_trading_dates_and_prior_map(
    histories: Mapping[str, Mapping[date, Mapping[str, object]]],
    *,
    coverage_start: date,
    coverage_end: date,
) -> tuple[tuple[date, ...], Mapping[date, date]]:
    """Derive observed GC trading sessions without a hindsight holiday calendar."""
    all_dates = sorted({d for rows in histories.values() for d in rows})
    dates = tuple(d for d in all_dates if coverage_start <= d <= coverage_end)
    if not dates:
        raise ValueError("no observed GC trading sessions inside coverage")
    prior: dict[date, date] = {}
    for d in dates:
        earlier = [p for p in all_dates if p < d]
        if not earlier:
            raise ValueError(f"no completed prior GC session available for {d.isoformat()}")
        prior[d] = earlier[-1]
    return dates, prior


def build_daily_liquidity_responses(
    *,
    master: ContractMaster,
    histories: Mapping[str, Mapping[date, Mapping[str, object]]],
    dates: Sequence[date],
    prior_session_date_by_as_of: Mapping[date, date],
) -> Mapping[date, Mapping[str, Sequence[Mapping[str, object]]]]:
    """Materialize explicit response-or-zero evidence for every eligible contract."""
    requests = build_master_liquidity_request_plan(
        master,
        dates=dates,
        prior_session_date_by_as_of=prior_session_date_by_as_of,
        roll_buffer_days=ROLL_BUFFER_DAYS,
        max_settlement_days_forward=MAX_SETTLEMENT_DAYS_FORWARD,
    )
    out: dict[date, Mapping[str, Sequence[Mapping[str, object]]]] = {}
    for request in requests:
        per_contract: dict[str, Sequence[Mapping[str, object]]] = {}
        for ticker in request.contracts:
            if ticker not in histories:
                raise ValueError(f"session history was not acquired for eligible contract {ticker}")
            row = histories[ticker].get(request.session_date)
            # Complete 1session history with no row is explicit zero traded volume.
            per_contract[ticker] = () if row is None else (row,)
        out[request.as_of] = per_contract
    return out


def acquire_raw_pages_for_selected_chain(
    get_json: JsonGet,
    *,
    master: ContractMaster,
    dates: Sequence[date],
    prior_session_date_by_as_of: Mapping[date, date],
    liquidity_responses_by_as_of: Mapping[date, Mapping[str, Sequence[Mapping[str, object]]]],
) -> Mapping[str, Sequence[Mapping[str, Any]]]:
    """Acquire complete 1m cursor chains for the selected causal front windows."""
    # A dry dataset build is not possible before pages exist, so reconstruct just the
    # request/calendar selection using the public deterministic components.
    from gold_cio_v9.data.master_front_calendar import build_master_liquid_front_calendar
    from gold_cio_v9.data.evidence_dataset_pipeline import build_liquid_contract_fetch_plan

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
    windows = build_liquid_contract_fetch_plan(calendar)
    pages: dict[str, Sequence[Mapping[str, Any]]] = {}
    for window in windows:
        chain = fetch_all_pages(
            get_json,
            path=f"/futures/v1/aggs/{window.contract}",
            params={
                "resolution": "1min",
                "window_start.gte": window.query_window_start_gte.isoformat(),
                "window_start.lte": window.query_window_start_lte.isoformat(),
                "sort": "window_start.asc",
                "limit": 50000,
            },
        )
        if not any(page.get("results") for page in chain):
            raise ValueError(f"no 1m bars returned for selected contract {window.contract}")
        pages[window.contract] = chain
    return pages


def acquire_exp0001_massive_evidence(
    get_json: JsonGet,
    *,
    master: ContractMaster,
    coverage_start: date,
    coverage_end: date,
) -> MasterEvidenceResult:
    """Acquire and assemble the full locked data-only EXP-0001 GC evidence dataset."""
    histories = acquire_session_histories(
        get_json, master=master, coverage_start=coverage_start, coverage_end=coverage_end,
    )
    dates, prior = derive_trading_dates_and_prior_map(
        histories, coverage_start=coverage_start, coverage_end=coverage_end,
    )
    responses = build_daily_liquidity_responses(
        master=master, histories=histories, dates=dates,
        prior_session_date_by_as_of=prior,
    )
    pages = acquire_raw_pages_for_selected_chain(
        get_json, master=master, dates=dates,
        prior_session_date_by_as_of=prior,
        liquidity_responses_by_as_of=responses,
    )
    return build_master_evidence_dataset(
        master=master,
        dates=dates,
        prior_session_date_by_as_of=prior,
        liquidity_responses_by_as_of=responses,
        pages_by_contract=pages,
    )


def dump_authoritative_bars_jsonl(result: MasterEvidenceResult, path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        for b in result.dataset.bars:
            payload = {
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
            f.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")


def lineage_payload(lineage: AcquisitionLineageManifest) -> dict[str, object]:
    return {
        "roll_buffer_days": lineage.roll_buffer_days,
        "roll_buffer_bars": lineage.roll_buffer_bars,
        "max_settlement_days_forward": lineage.max_settlement_days_forward,
        "contract_master_hash": lineage.contract_master_hash,
        "decisions": [asdict(d) for d in lineage.decisions],
        "fetch_windows": [list(x) for x in lineage.fetch_windows],
        "dataset_hash": lineage.dataset_hash,
        "lineage_hash": lineage.lineage_hash,
    }


def dump_acquisition_lineage_json(result: MasterEvidenceResult, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(lineage_payload(result.lineage), sort_keys=True, indent=2, allow_nan=False),
        encoding="utf-8",
    )
