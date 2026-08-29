"""Immutable GC outright contract master for causal evidence acquisition.

Massive's historical ``active`` reference flag is not reliable enough to define the
tradable candidate universe: we observed a contract with real session volume absent
from an active-only PIT snapshot. Contract expiry/listing specifications are fixed
contract metadata, so EXP-0001 V3 binds one immutable master registry and derives
eligibility mechanically from first/last trade dates rather than the provider's
historical active flag.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
import json
import re
from typing import Mapping, Sequence

from gold_cio_v9.data.contract_chain import ContractSpec

_GC_OUTRIGHT = re.compile(r"^GC[FGHJKMNQUVXZ]\d{1,2}$")


@dataclass(frozen=True)
class ContractMaster:
    specs: tuple[ContractSpec, ...]
    master_hash: str


def _date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be ISO date text")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid {field}") from exc


def build_gc_contract_master(rows: Sequence[Mapping[str, object]]) -> ContractMaster:
    if not rows:
        raise ValueError("contract master rows are required")
    by_ticker: dict[str, ContractSpec] = {}
    for row in rows:
        ticker = str(row.get("ticker", ""))
        if not _GC_OUTRIGHT.fullmatch(ticker):
            continue
        if row.get("product_code") != "GC":
            continue
        spec = ContractSpec(
            ticker=ticker,
            first_trade_date=_date(row.get("first_trade_date"), "first_trade_date"),
            last_trade_date=_date(row.get("last_trade_date"), "last_trade_date"),
            settlement_date=_date(row.get("settlement_date"), "settlement_date"),
        )
        if spec.first_trade_date > spec.last_trade_date:
            raise ValueError(f"invalid contract lifespan for {ticker}")
        previous = by_ticker.get(ticker)
        if previous is not None and previous != spec:
            raise ValueError(f"inconsistent immutable contract metadata for {ticker}")
        by_ticker[ticker] = spec
    if not by_ticker:
        raise ValueError("no valid outright GC contract specs")
    specs = tuple(sorted(by_ticker.values(), key=lambda s: (s.settlement_date, s.ticker)))
    payload = [
        {"ticker": s.ticker, "first_trade_date": s.first_trade_date.isoformat(), "last_trade_date": s.last_trade_date.isoformat(), "settlement_date": s.settlement_date.isoformat()}
        for s in specs
    ]
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ContractMaster(specs, digest)


def eligible_master_contracts(
    master: ContractMaster,
    *,
    as_of: date,
    roll_buffer_days: int = 5,
    max_settlement_days_forward: int = 365,
) -> tuple[ContractSpec, ...]:
    if roll_buffer_days < 0 or max_settlement_days_forward <= 0:
        raise ValueError("invalid contract-universe bounds")
    latest_settlement = as_of + timedelta(days=max_settlement_days_forward)
    eligible = tuple(
        s for s in master.specs
        if s.first_trade_date <= as_of <= s.last_trade_date - timedelta(days=roll_buffer_days)
        and s.settlement_date <= latest_settlement
    )
    if not eligible:
        raise ValueError("no eligible contracts in immutable master universe")
    return eligible
