"""Causal GC front calendar using the immutable contract master registry."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from gold_cio_v9.data.causal_roll import PriorSessionLiquidity, select_causal_liquid_front
from gold_cio_v9.data.contract_master import ContractMaster, eligible_master_contracts
from gold_cio_v9.data.liquid_front_calendar import LiquidFrontCalendar, LiquidFrontDay
from gold_cio_v9.data.prior_session_liquidity import build_prior_session_liquidity


@dataclass(frozen=True)
class MasterLiquidityRequest:
    as_of: date
    session_date: date
    contracts: tuple[str, ...]


def build_master_liquidity_request_plan(
    master: ContractMaster,
    *, dates: Sequence[date], prior_session_date_by_as_of: Mapping[date, date],
    roll_buffer_days: int = 5, max_settlement_days_forward: int = 365,
) -> tuple[MasterLiquidityRequest, ...]:
    if not dates or len(set(dates)) != len(dates) or any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValueError("dates must be non-empty, unique and strictly increasing")
    out = []
    for as_of in dates:
        prior = prior_session_date_by_as_of.get(as_of)
        if prior is None or prior >= as_of:
            raise ValueError(f"invalid prior session date for {as_of.isoformat()}")
        specs = eligible_master_contracts(master, as_of=as_of, roll_buffer_days=roll_buffer_days, max_settlement_days_forward=max_settlement_days_forward)
        out.append(MasterLiquidityRequest(as_of, prior, tuple(s.ticker for s in specs)))
    if set(prior_session_date_by_as_of) != set(dates):
        raise ValueError("prior-session mapping must exactly match requested dates")
    return tuple(out)


def build_master_liquid_front_calendar(
    master: ContractMaster,
    *, requests: Sequence[MasterLiquidityRequest],
    responses_by_as_of: Mapping[date, Mapping[str, Sequence[Mapping[str, object]]]],
    roll_buffer_days: int = 5, max_settlement_days_forward: int = 365,
) -> LiquidFrontCalendar:
    if not requests:
        raise ValueError("master liquidity requests are required")
    out = []
    order = []
    seen = set()
    for request in requests:
        responses = responses_by_as_of.get(request.as_of)
        if responses is None:
            raise ValueError(f"missing liquidity responses for {request.as_of.isoformat()}")
        snapshot = build_prior_session_liquidity(responses, expected_contracts=request.contracts, session_date=request.session_date)
        specs = eligible_master_contracts(master, as_of=request.as_of, roll_buffer_days=roll_buffer_days, max_settlement_days_forward=max_settlement_days_forward)
        expected = tuple(s.ticker for s in specs)
        if request.contracts != expected:
            raise ValueError("request universe diverges from immutable contract master")
        contract = select_causal_liquid_front(specs, as_of=request.as_of, prior_liquidity=snapshot, roll_buffer_days=roll_buffer_days)
        out.append(LiquidFrontDay(request.as_of, request.session_date, contract))
        if contract not in seen:
            seen.add(contract)
            order.append(contract)
    if set(responses_by_as_of) != {r.as_of for r in requests}:
        raise ValueError("liquidity response dates must exactly match request plan")
    rank = {c: i for i, c in enumerate(order)}
    last = -1
    for day in out:
        r = rank[day.contract]
        if r < last:
            raise ValueError("master calendar re-enters an older selected contract")
        last = r
    return LiquidFrontCalendar(tuple(out), tuple(order))
