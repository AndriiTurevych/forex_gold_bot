"""Deterministic Massive GC acquisition planning and page-completeness checks.

Futures evidence is assigned by Massive ``session_end_date`` rather than the UTC
calendar date of each minute bar. A GC session opens the prior evening, so filtering
raw bars by ``window_start`` date would systematically drop the opening portion of
every assigned session and admit part of the following session. Formal evidence
therefore uses the session-aware parser below.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
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

    @property
    def query_window_start_gte(self) -> date:
        """Massive window_start lower bound needed to capture the first session."""
        return self.start_date - timedelta(days=1)

    @property
    def query_window_start_lte(self) -> date:
        """Inclusive upper query bound; next-session rows are filtered by session date."""
        return self.end_date


def build_contract_fetch_plan(calendar: FrontContractCalendar) -> tuple[ContractFetchWindow, ...]:
    """Compress daily PIT assignments into one immutable session window per contract."""
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


def _collect_complete_pages(pages: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if not pages:
        raise ValueError("Massive aggregate pages are required")
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
    return rows


def parse_complete_massive_gc_pages(
    pages: Sequence[Mapping[str, Any]],
    *,
    expected_contract: str,
    start_date: date,
    end_date: date,
) -> tuple[HistoricalBar, ...]:
    """Legacy UTC-date parser retained for non-formal diagnostics and old callers."""
    if end_date < start_date:
        raise ValueError("end_date precedes start_date")
    if not expected_contract.startswith("GC") or "-" in expected_contract:
        raise ValueError("expected_contract must be outright GC")
    rows = _collect_complete_pages(pages)
    bars = parse_massive_gc_aggs(rows)
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
    for bar in bars:
        if bar.contract != expected_contract:
            raise ValueError("aggregate response contains unexpected contract")
        if not (start_dt <= bar.event_time <= end_dt):
            raise ValueError("aggregate response contains bar outside requested date window")
    return tuple(bars)


def parse_complete_massive_gc_session_pages(
    pages: Sequence[Mapping[str, Any]],
    *,
    expected_contract: str,
    start_session_date: date,
    end_session_date: date,
) -> tuple[HistoricalBar, ...]:
    """Normalize only bars assigned to the requested GC trading-session dates.

    The caller should query Massive ``window_start`` from ``start_session_date-1``
    through ``end_session_date``. Rows from the one-day query padding are expected
    and are filtered solely by ``session_end_date``. Every raw row must still be the
    requested outright contract, and every selected bar must start no earlier than
    the calendar day immediately preceding its declared session end date.
    """
    if end_session_date < start_session_date:
        raise ValueError("end_session_date precedes start_session_date")
    if not expected_contract.startswith("GC") or "-" in expected_contract:
        raise ValueError("expected_contract must be outright GC")

    raw_rows = _collect_complete_pages(pages)
    selected: list[Mapping[str, Any]] = []
    session_by_ns: dict[int, date] = {}
    for row in raw_rows:
        if str(row.get("ticker", "")) != expected_contract:
            raise ValueError("aggregate response contains unexpected contract")
        raw_session = row.get("session_end_date")
        if not isinstance(raw_session, str):
            raise ValueError("formal GC aggregate row is missing session_end_date")
        try:
            session_date = date.fromisoformat(raw_session)
        except ValueError as exc:
            raise ValueError("invalid Massive session_end_date") from exc
        if start_session_date <= session_date <= end_session_date:
            raw_ns = row.get("window_start")
            if isinstance(raw_ns, bool) or not isinstance(raw_ns, (int, float)):
                raise ValueError("invalid Massive window_start")
            ns = int(raw_ns)
            if ns in session_by_ns:
                raise ValueError("duplicate aggregate bar across session pages")
            session_by_ns[ns] = session_date
            selected.append(row)

    if not selected:
        raise ValueError("no Massive bars found for requested session window")

    bars = parse_massive_gc_aggs(selected)
    for bar in bars:
        if bar.contract != expected_contract:
            raise ValueError("aggregate response contains unexpected contract")
        ns = int(bar.event_time.timestamp() * 1_000_000_000)
        session_date = session_by_ns.get(ns)
        if session_date is None:
            raise RuntimeError("normalized bar lost Massive session identity")
        event_day = bar.event_time.astimezone(timezone.utc).date()
        if not (session_date - timedelta(days=1) <= event_day <= session_date):
            raise ValueError("bar timestamp is inconsistent with Massive session_end_date")
    return tuple(bars)
