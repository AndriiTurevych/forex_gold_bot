#!/usr/bin/env python3
"""Inventory outcome-free GC aggregate access under the current Massive plan."""
from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


BASE = "https://api.massive.com/futures/v1/aggs"
PROBES = (
    {"label": "EXP0002_START", "ticker": "GCG2", "start": "2022-01-03", "end": "2022-01-05"},
    {"label": "AVAILABLE_TAIL", "ticker": "GCG5", "start": "2025-01-13", "end": "2025-01-15"},
    {"label": "EXP0002_END", "ticker": "GCJ5", "start": "2025-03-30", "end": "2025-04-01"},
)


def probe(item: dict[str, str], key: str) -> dict[str, object]:
    query = urlencode({
        "resolution": "1min",
        "window_start.gte": item["start"],
        "window_start.lte": item["end"],
        "limit": 10,
        "sort": "window_start.asc",
        "apiKey": key,
    })
    url = f"{BASE}/{item['ticker']}?{query}"
    result: dict[str, object] = {**item, "resolution": "1min"}
    try:
        with urlopen(url, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as exc:
        return {**result, "access": "BLOCKED", "http_status": exc.code}
    except (URLError, TimeoutError):
        return {**result, "access": "TRANSPORT_ERROR"}
    rows = payload.get("results", [])
    valid = [row for row in rows if {"ticker", "window_start", "open", "high", "low", "close", "volume"} <= set(row)]
    return {
        **result,
        "access": "READY" if valid else "NO_ROWS",
        "rows_returned": len(rows),
        "valid_rows": len(valid),
    }


def main() -> int:
    key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not key:
        print(json.dumps({"error": "MASSIVE_API_KEY is required"}), file=sys.stderr)
        return 2
    probes = [probe(item, key) for item in PROBES]
    result = {
        "schema": "gold-cio-aggregate-access-inventory-v1",
        "experiment_id": "EXP-0002",
        "purpose": "outcome_free_data_inventory",
        "probes": probes,
        "strategy_outcomes_generated": False,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if any(item["access"] == "READY" for item in probes) else 2


if __name__ == "__main__":
    raise SystemExit(main())
