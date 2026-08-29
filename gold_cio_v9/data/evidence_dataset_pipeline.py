"""End-to-end deterministic assembly of causal raw-contract GC evidence data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

from gold_cio_v9.data.causal_roll import MAX_SETTLEMENT_DAYS_FORWARD, causal_front_candidates
from gold_cio_v9.data.dataset_assembly import assemble_gc_dataset
from gold_cio_v9.data.dataset_manifest import DatasetManifest, build_gc_dataset_manifest
from gold_cio_v9.data.governance import HistoricalBar
from gold_cio_v9.data.liquid_front_calendar import LiquidFrontCalendar, build_liquid_front_calendar
from gold_cio_v9.data.massive_contracts import parse_massive_gc_contracts
from gold_cio_v9.data.massive_fetch_plan import ContractFetchWindow, parse_complete_massive_gc_session_pages
from gold_cio_v9.data.prior_session_liquidity import build_prior_session_liquidity


@dataclass(frozen=True)
class LiquidityRequest:
    as_of: date
    session_date: date
    contracts: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceDatasetResult:
    calendar: LiquidFrontCalendar
    fetch_windows: tuple[ContractFetchWindow, ...]
    bars: tuple[HistoricalBar, ...]
    manifest: DatasetManifest


def build_liquidity_request_plan(
    snapshots: Mapping[date, Sequence[Mapping[str, object]]],
    *,
    dates: Sequence[date],
    prior_session_date_by_as_of: Mapping[date, date],
    roll_buffer_days: int = 5,
    max_settlement_days_forward: int = MAX_SETTLEMENT_DAYS_FORWARD,
) -> tuple[LiquidityRequest, ...]:
    if not dates:
        raise ValueError("dates are required")
    if len(set(dates)) != len(dates):
        raise ValueError("dates contain duplicates")
    if any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValueError("dates must be strictly increasing")

    requests: list[LiquidityRequest] = []
    for as_of in dates:
        rows = snapshots.get(as_of)
        if rows is None:
            raise ValueError(f"missing PIT contract snapshot for {as_of.isoformat()}")
        session_date = prior_session_date_by_as_of.get(as_of)
        if session_date is None:
            raise ValueError(f"missing prior session date for {as_of.isoformat()}")
        if session_date >= as_of:
            raise ValueError("prior session date must be strictly before as_of")
        specs = parse_massive_gc_contracts(rows, as_of=as_of)
        candidates = causal_front_candidates(
            specs, as_of=as_of, roll_buffer_days=roll_buffer_days,
            max_settlement_days_forward=max_settlement_days_forward,
        )
        requests.append(LiquidityRequest(as_of, session_date, tuple(spec.ticker for spec in candidates)))

    unexpected = set(prior_session_date_by_as_of) - set(dates)
    if unexpected:
        raise ValueError("prior-session mapping contains dates outside requested range")
    return tuple(requests)


def build_calendar_from_liquidity_responses(
    snapshots: Mapping[date, Sequence[Mapping[str, object]]],
    *,
    requests: Sequence[LiquidityRequest],
    responses_by_as_of: Mapping[date, Mapping[str, Sequence[Mapping[str, object]]]],
    roll_buffer_days: int = 5,
    max_settlement_days_forward: int = MAX_SETTLEMENT_DAYS_FORWARD,
) -> LiquidFrontCalendar:
    if not requests:
        raise ValueError("liquidity requests are required")
    dates = tuple(r.as_of for r in requests)
    if len(set(dates)) != len(dates) or any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValueError("liquidity requests must be unique and chronological")

    prior = {}
    for request in requests:
        responses = responses_by_as_of.get(request.as_of)
        if responses is None:
            raise ValueError(f"missing liquidity responses for {request.as_of.isoformat()}")
        prior[request.as_of] = build_prior_session_liquidity(
            responses, expected_contracts=request.contracts, session_date=request.session_date,
        )

    unexpected = set(responses_by_as_of) - set(dates)
    if unexpected:
        raise ValueError("liquidity responses contain dates outside request plan")
    return build_liquid_front_calendar(
        snapshots, prior, dates=dates, roll_buffer_days=roll_buffer_days,
        max_settlement_days_forward=max_settlement_days_forward,
    )


def build_liquid_contract_fetch_plan(calendar: LiquidFrontCalendar) -> tuple[ContractFetchWindow, ...]:
    """Compress front assignments into windows of session_end_date, not UTC bar dates."""
    if not calendar.days or not calendar.contract_order:
        raise ValueError("liquid front calendar is empty")
    windows: list[ContractFetchWindow] = []
    seen: set[str] = set()
    current = calendar.days[0].contract
    start = calendar.days[0].as_of
    previous = calendar.days[0].as_of
    for day in calendar.days[1:]:
        if day.as_of <= previous:
            raise ValueError("calendar dates must be strictly increasing")
        if day.contract != current:
            windows.append(ContractFetchWindow(current, start, previous))
            seen.add(current)
            if day.contract in seen:
                raise ValueError("fetch plan would re-enter an older contract")
            current = day.contract
            start = day.as_of
        previous = day.as_of
    windows.append(ContractFetchWindow(current, start, previous))
    if tuple(w.contract for w in windows) != calendar.contract_order:
        raise ValueError("fetch-plan order does not match causal contract_order")
    return tuple(windows)


def assemble_evidence_dataset(
    calendar: LiquidFrontCalendar,
    *,
    pages_by_contract: Mapping[str, Sequence[Mapping[str, Any]]],
    roll_buffer_bars: int = 0,
) -> EvidenceDatasetResult:
    """Assemble only the exact trading sessions assigned to each causal front.

    Fetch pages may include the one-day ``window_start`` padding required by Massive
    to capture the prior-evening opening of the first requested futures session.
    The session-aware parser removes padding by ``session_end_date`` before bars are
    normalized and stitched.
    """
    windows = build_liquid_contract_fetch_plan(calendar)
    planned = tuple(w.contract for w in windows)
    if set(pages_by_contract) != set(planned):
        missing = sorted(set(planned) - set(pages_by_contract))
        extra = sorted(set(pages_by_contract) - set(planned))
        raise ValueError(f"aggregate page coverage mismatch missing={missing} extra={extra}")
    contract_bars: dict[str, tuple[HistoricalBar, ...]] = {}
    for window in windows:
        contract_bars[window.contract] = parse_complete_massive_gc_session_pages(
            pages_by_contract[window.contract],
            expected_contract=window.contract,
            start_session_date=window.start_date,
            end_session_date=window.end_date,
        )
    bars = assemble_gc_dataset(
        contract_bars, contract_order=calendar.contract_order,
        roll_buffer_bars=roll_buffer_bars,
    )
    manifest = build_gc_dataset_manifest(bars)
    if manifest.contracts != calendar.contract_order:
        raise ValueError("manifest contract order diverges from causal calendar")
    return EvidenceDatasetResult(calendar, windows, bars, manifest)
