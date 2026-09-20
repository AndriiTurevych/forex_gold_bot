#!/usr/bin/env python3
"""Collect, validate, and securely publish one XAUUSD MT5 snapshot to MIDAS."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gold_cio_v9.data.mt5_snapshot import validate_snapshot
from gold_cio_v9.live.decision_pipeline import build_decision
from gold_cio_v9.live.mt5_analysis import analyze_snapshot
from scripts.collect_mt5_xauusd import collect

DEFAULT_URL = "https://jqmzpwkdbcuqnykhfmvc.supabase.co/functions/v1/ingest-mt5"


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--bars", type=int, default=2880)
    parser.add_argument("--server-utc-offset-hours", type=float, default=3.0)
    parser.add_argument("--terminal-path")
    parser.add_argument("--mt5-timeout-ms", type=int, default=10_000)
    parser.add_argument("--output", default="mt5_artifacts/snapshot.json")
    parser.add_argument("--url", default=os.environ.get("MIDAS_INGEST_URL", DEFAULT_URL))
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()

    token = os.environ.get("MIDAS_INGEST_TOKEN", "").strip()
    if not token:
        raise RuntimeError("MIDAS_INGEST_TOKEN is not set")

    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError("MetaTrader5 package is required on the Windows MT5 host") from exc

    snapshot = collect(
        mt5,
        symbol=args.symbol,
        bar_count=args.bars,
        terminal_path=args.terminal_path,
        server_utc_offset_hours=args.server_utc_offset_hours,
        mt5_timeout_ms=args.mt5_timeout_ms,
    )
    output = Path(args.output)
    _atomic_json(output, snapshot)

    readiness = validate_snapshot(
        snapshot,
        observed_at=datetime.now(timezone.utc),
        expected_symbol=args.symbol,
    )
    preflight = readiness.as_dict()
    if not readiness.broker_feed_ready:
        raise RuntimeError(f"BROKER_FEED_NOT_READY:{readiness.reason}")

    equity_raw = os.environ.get("MIDAS_SHADOW_EQUITY", "").strip()
    shadow_equity = float(equity_raw) if equity_raw else None
    analysis = analyze_snapshot(snapshot, shadow_equity=shadow_equity)
    _atomic_json(output.with_name("analysis.json"), analysis)

    # MIDAS v2 control plane. This creates a local shadow/demo decision artifact
    # while preserving the existing ingest payload contract below.
    decision = build_decision(
        snapshot,
        analysis=analysis,
        shadow_equity=shadow_equity,
    )
    _atomic_json(output.with_name("decision.json"), decision)

    body = json.dumps(
        {"snapshot": snapshot, "preflight": preflight, "analysis": analysis},
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    request = Request(
        args.url,
        data=body,
        method="POST",
        headers={
            "content-type": "application/json",
            "x-midas-ingest-token": token,
            "user-agent": "midas-mt5-bridge/2",
        },
    )
    try:
        with urlopen(request, timeout=args.timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MIDAS_UPLOAD_HTTP_{exc.code}:{detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"MIDAS_UPLOAD_NETWORK_ERROR:{exc.reason}") from exc

    if result.get("ok") is not True:
        raise RuntimeError(f"MIDAS_UPLOAD_REJECTED:{result}")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
