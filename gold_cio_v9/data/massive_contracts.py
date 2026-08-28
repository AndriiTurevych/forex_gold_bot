"""Point-in-time Massive futures contract metadata adapter for GC research.

Massive's contracts endpoint may include calendar/combo symbols even when `type`
reports `single`. This adapter therefore validates the ticker grammar explicitly
and emits only outright COMEX Gold futures metadata usable by the deterministic
contract-chain policy. It performs no volume/OI ranking and no hindsight roll
selection.
"""
from __future__ import annotations

from datetime import date
import re
from typing import Mapping, Sequence

from gold_cio_v9.data.contract_chain import ContractSpec, select_front_contract

_GC_OUTRIGHT = re.compile(r"^GC[FGHJKMNQUVXZ]\d{1,2}$")


def _parse_date(value: object, *, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD text")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid {field}") from exc


def parse_massive_gc_contracts(
    rows: Sequence[Mapping[str, object]],
    *,
    as_of: date,
) -> tuple[ContractSpec, ...]:
    """Parse one PIT Massive contract snapshot into outright GC ContractSpecs.

    Required safeguards:
    - every accepted row must be product_code GC and active on `as_of`;
    - ticker must match an outright GC month-code contract exactly;
    - row `date`, when supplied, must equal `as_of`;
    - duplicate outright tickers fail closed;
    - chronology is delegated to ContractSpec validation.
    """
    if not rows:
        raise ValueError("contract metadata rows are required")

    out: list[ContractSpec] = []
    seen: set[str] = set()
    for row in rows:
        ticker = row.get("ticker")
        if not isinstance(ticker, str) or not _GC_OUTRIGHT.fullmatch(ticker):
            continue
        if row.get("product_code") != "GC":
            continue
        if row.get("active") is not True:
            continue
        row_date = row.get("date")
        if row_date is not None and _parse_date(row_date, field="date") != as_of:
            raise ValueError("point-in-time metadata date mismatch")
        if ticker in seen:
            raise ValueError(f"duplicate outright contract metadata for {ticker}")
        seen.add(ticker)
        out.append(
            ContractSpec(
                ticker=ticker,
                first_trade_date=_parse_date(row.get("first_trade_date"), field="first_trade_date"),
                last_trade_date=_parse_date(row.get("last_trade_date"), field="last_trade_date"),
                settlement_date=_parse_date(row.get("settlement_date"), field="settlement_date"),
            )
        )

    if not out:
        raise ValueError("no active outright GC contracts in PIT metadata")
    return tuple(sorted(out, key=lambda s: (s.settlement_date, s.ticker)))


def select_massive_gc_front(
    rows: Sequence[Mapping[str, object]],
    *,
    as_of: date,
    roll_buffer_days: int = 5,
) -> str | None:
    """Select the deterministic front contract from one PIT Massive snapshot."""
    specs = list(parse_massive_gc_contracts(rows, as_of=as_of))
    return select_front_contract(specs, as_of, roll_buffer_days=roll_buffer_days)
