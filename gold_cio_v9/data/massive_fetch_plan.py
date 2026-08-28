"""Deterministic Massive GC acquisition planning and page-completeness checks.

This module bridges the PIT front-contract calendar to raw contract-level 1-minute
Massive aggregates. It does not perform network I/O itself. Instead it makes the
required fetch windows explicit and validates that a caller supplied the complete
pagination chain before bars may enter dataset assembly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Mapping, Sequence, Any

from gold_cio_v9.data.front_calendar import FrontContractCalendar
from gold_cio_v9.data.governance import HistoricalBar
from gold_cio_v9.data.massive_gc import parse_massive_gc_aggs


@dataclass(frozen=True)
class ContractFetchWindow:
    contract: str
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if not self.contract.startswith("GC") or "-" in self.contract:
            raise ValueError("fetch window requires outright GC contract")
        if self.end_date < self.start_date:
            raise ValueError("fetch window end precedes start")


def build_contract_fetch_plan(calendar: FrontContractCalendar) -> tuple[ContractFetchWindow, ...]:
    """Compress daily PIT assignments into one immutable fetch window per contract.

    Calendar dates may skip weekends/holidays; the fetch window intentionally spans
    those gaps because the Massive aggregate endpoint simply returns observed bars.
    Contract re-entry is forbidden by the calendar and rechecked here.
    """
    if not calendar.days:
        raise ValueError("front-contract calendar is empty")
    if not calendar.contract_order:
        raise ValueError("front-contract contract_order is empty")

    windows: list[ContractFetchWindow] = []
    seen: set[str] = set()
    current_contract = calendar.days[0].contract
    current_start = calendar.days[0].as_of
    previous_date = calendar.days[0].as_of

    for day in calendar.days[1:]:
        if day.as_of <= previous_date:
            raise ValueError("calendar dates must be strictly increasing")
        if day.contract != current_contract:
            windows.append(ContractFetchWindow(current_contract, current_start, previous_date))
            seen.add(current_contract)
            if day.contract in seen:
                raise ValueError("fetch plan would re-enter an older contract")
            current_contract = day.contract
            current_start = day.as_of
        previous_date = day.as_of

    windows.append(ContractFetchWindow(current_contract, current_start, previous_date))

    order = tuple(w.contract for w in windows)
    if order != calendar.contract_order:
        raise ValueError("fetch-plan order does not match PIT contract_order")
    return tuple(windows)


def parse_complete_massive_gc_pages(
    pages: Sequence[Mapping[str, Any]],
    *,
    expected_contract: str,
    start_date: date,
    end_date: date,
) -> tuple[HistoricalBar, ...]:
    """Validate a complete Massive pagination chain and normalize all aggregate rows.

    Safeguards:
    - at least one response page is required;
    - every non-final page must advertise a next_url;
    - the final supplied page must not advertise a next_url (otherwise acquisition
      is incomplete and evidence assembly fails closed);
    - request IDs, when present, must not repeat;
    - every normalized bar must belong to the requested outright contract and fall
      within the inclusive UTC date window;
    - duplicate bars across page boundaries are rejected by the aggregate adapter.
    """
    if not pages:
        raise ValueError("Massive aggregate pages are required")
    if end_date < start_date:
        raise ValueError("end_date precedes start_date")
    if not expected_contract.startswith("GC") or "-" in expected_contract:
        raise ValueError("expected_contract must be outright GC")

    rows: list[Mapping[str, Any]] = []
    request_ids: set[str] = set()
    for i, page in enumerate(pages):
        results = page.get("results")
        if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
            raise ValueError("Massive page results must be a sequence")
        if not results:
            raise ValueError("Massive aggregate page contains no results")
        next_url = page.get("next_url")
        is_final = i == len(pages) - 1
        if not is_final and not next_url:
            raise ValueError("pagination chain terminates before supplied final page")
        if is_final and next_url:
            raise ValueError("Massive aggregate pagination is incomplete")
        request_id = page.get("request_id")
        if request_id is not None:
            rid = str(request_id)
            if rid in request_ids:
                raise ValueError("duplicate Massive request_id in pagination chain")
            request_ids.add(rid)
        for row in results:
            if not isinstance(row, Mapping):
                raise ValueError("Massive aggregate result row must be a mapping")
            rows.append(row)

    bars = parse_massive_gc_aggs(rows)
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
    for bar in bars:
        if bar.contract != expected_contract:
            raise ValueError("aggregate response contains unexpected contract")
        if not (start_dt <= bar.event_time <= end_dt):
            raise ValueError("aggregate response contains bar outside requested date window")
    return tuple(bars)
