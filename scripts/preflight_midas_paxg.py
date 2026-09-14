#!/usr/bin/env python3
"""Acquire a public PAXGUSDT snapshot and write an outcome-free preflight artifact."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from gold_cio_v9.data.binance_paxg import evaluate_proxy_readiness


BASE_URLS = (
    "https://data-api.binance.vision",
    "https://api.binance.com",
)


def _get(path: str, params: dict[str, object]) -> tuple[object, bytes, str]:
    failures: list[str] = []
    for base_url in BASE_URLS:
        url = f"{base_url}{path}?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": "gold-cio-midas-paxg-preflight/1"})
        try:
            with urlopen(request, timeout=15) as response:
                raw = response.read()
            return json.loads(raw), raw, base_url
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            failures.append(f"{base_url}:{type(exc).__name__}")
    raise RuntimeError("all public market-data endpoints failed: " + ",".join(failures))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="midas_paxg_artifacts/preflight.json")
    args = parser.parse_args()
    output = Path(args.output)

    try:
        book, raw_book, book_origin = _get(
            "/api/v3/ticker/bookTicker", {"symbol": "PAXGUSDT"}
        )
        klines, raw_klines, klines_origin = _get(
            "/api/v3/klines", {"symbol": "PAXGUSDT", "interval": "1m", "limit": 10}
        )
        acquired_at = datetime.now(timezone.utc)
        result = evaluate_proxy_readiness(
            quote_payload=book,
            kline_rows=klines,
            acquired_at=acquired_at,
            max_bar_age=timedelta(seconds=120),
            max_spread_bps=2.0,
        )
        result["book_origin"] = book_origin
        result["klines_origin"] = klines_origin
        result["raw_book_sha256"] = sha256(raw_book).hexdigest()
        result["raw_klines_sha256"] = sha256(raw_klines).hexdigest()
        _write(output, result)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["data_ready"] else 2
    except Exception as exc:
        failure = {
            "schema": "gold-cio-paxg-proxy-preflight-v1",
            "experiment_id": "EXP-0006",
            "instrument_role": "GOLD_PROXY_ONLY",
            "status": "VETO",
            "data_ready": False,
            "reasons": ["ACQUISITION_OR_VALIDATION_FAILURE"],
            "error_type": type(exc).__name__,
            "strategy_outcomes_generated": False,
            "formal_gc_verdict_allowed": False,
            "real_orders_allowed": False,
        }
        _write(output, failure)
        print(json.dumps(failure, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
