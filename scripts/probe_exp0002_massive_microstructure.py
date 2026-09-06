#!/usr/bin/env python3
"""Outcome-free entitlement and schema probe for EXP-0002 tick evidence."""
from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


BASE = "https://api.massive.com"
TICKER = "GCG5"
SESSION_DATE = "2025-01-15"


def _get(kind: str, key: str) -> list[dict]:
    query = urlencode({
        "session_end_date": SESSION_DATE,
        "limit": 1000,
        "sort": "timestamp.asc",
        "apiKey": key,
    })
    try:
        with urlopen(f"{BASE}/futures/v1/{kind}/{TICKER}?{query}", timeout=30) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"{kind} entitlement probe returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"{kind} entitlement probe transport failure") from exc
    if payload.get("status") != "OK":
        raise RuntimeError(f"{kind} entitlement probe did not return OK")
    rows = payload.get("results")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"{kind} entitlement probe returned no rows")
    return rows


def main() -> int:
    key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("MASSIVE_API_KEY is required")
    trades = _get("trades", key)
    quotes = _get("quotes", key)
    trade_fields = {"ticker", "timestamp", "price", "size", "session_end_date", "sequence_number"}
    quote_fields = {
        "ticker", "timestamp", "bid_price", "ask_price", "bid_size", "ask_size",
        "session_end_date", "sequence_number",
    }
    complete_trades = [row for row in trades if trade_fields <= set(row)]
    complete_quotes = [row for row in quotes if quote_fields <= set(row)]
    if not complete_trades:
        raise RuntimeError("trade schema is incomplete for EXP-0002")
    if not complete_quotes:
        raise RuntimeError("quote schema is incomplete for EXP-0002")
    print(json.dumps({
        "experiment_id": "EXP-0002",
        "provider": "Massive",
        "ticker": TICKER,
        "session_end_date": SESSION_DATE,
        "trades_returned": len(trades),
        "complete_trades": len(complete_trades),
        "quotes_returned": len(quotes),
        "complete_quotes": len(complete_quotes),
        "microstructure_entitlement": "READY",
        "strategy_outcomes_generated": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(json.dumps({
            "experiment_id": "EXP-0002",
            "microstructure_entitlement": "BLOCKED",
            "reason": str(exc),
            "strategy_outcomes_generated": False,
        }, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
