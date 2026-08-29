"""Build causal prior-session GC liquidity snapshots from completed Massive session bars.

The builder consumes an explicit response for every expected contract. An empty
completed response is interpreted as zero traded volume; a missing response is not.
This distinction lets the roll policy remain fail-closed while correctly handling
contracts that had no trades in the completed prior session.
"""
from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Mapping, Sequence

from gold_cio_v9.data.causal_roll import PriorSessionLiquidity


def build_prior_session_liquidity(
    responses_by_contract: Mapping[str, Sequence[Mapping[str, object]]],
    *,
    expected_contracts: Sequence[str],
    session_date: date,
) -> PriorSessionLiquidity:
    """Return one immutable prior-session volume snapshot.

    Each expected contract must have an explicit completed API response. A response
    may be empty (zero volume), but if it contains rows they must all identify the
    same expected outright contract and completed ``session_date``. Volumes are
    summed so the function is robust to providers returning more than one row.
    """
    if not expected_contracts:
        raise ValueError("expected_contracts are required")
    if len(set(expected_contracts)) != len(expected_contracts):
        raise ValueError("expected_contracts contain duplicates")

    volumes: dict[str, float] = {}
    for ticker in expected_contracts:
        if not isinstance(ticker, str) or not ticker.startswith("GC") or "-" in ticker:
            raise ValueError(f"invalid outright GC contract: {ticker!r}")
        if ticker not in responses_by_contract:
            raise ValueError(f"missing completed liquidity response for {ticker}")
        rows = responses_by_contract[ticker]
        total = 0.0
        for row in rows:
            if row.get("ticker") != ticker:
                raise ValueError(f"liquidity ticker mismatch for {ticker}")
            if row.get("session_end_date") != session_date.isoformat():
                raise ValueError(f"liquidity session date mismatch for {ticker}")
            raw = row.get("volume")
            try:
                volume = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid session volume for {ticker}") from exc
            if not isfinite(volume) or volume < 0:
                raise ValueError(f"invalid session volume for {ticker}")
            total += volume
        volumes[ticker] = total

    unexpected = set(responses_by_contract) - set(expected_contracts)
    if unexpected:
        raise ValueError(f"unexpected liquidity responses: {sorted(unexpected)!r}")

    return PriorSessionLiquidity(session_date=session_date, volume_by_contract=volumes)
