#!/usr/bin/env python3
"""Engineering-only EXP-0004 cycle. No order adapter or statistical verdict.

Use an explicitly initialized local ledger. Remote scheduling/restore is not
enabled until independent ledger anchoring and the validation protocol lock.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

from gold_cio_v9.forward_v4 import (
    EXPERIMENT, MINUTE, index_bars, pending_contracts, record_decision, settle, utc,
)
from gold_cio_v9.shadow.ledger import HashChainLedger
from scripts.acquire_shadow_massive import Massive, select_front
from scripts.build_exp0002_structural_windows import build_windows, load_bars


def collect(api, ledger: HashChainLedger, now: datetime, output: Path, clock=None) -> dict:
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = utc(now)
    contract, selection_session, selection_volume = select_front(api, now)
    contracts = sorted(pending_contracts(ledger) | {contract})
    raw_by_contract = {}
    for ticker in contracts:
        pages = api.pages(f"/futures/v1/aggs/{ticker}", {
            "resolution": "1min", "window_start.gte": int((now - timedelta(days=10)).timestamp()) * 1_000_000_000,
            "window_start.lte": int(now.timestamp()) * 1_000_000_000,
            "sort": "window_start.asc", "limit": 50000,
        })
        raw_by_contract[ticker] = [r for page in pages for r in page["results"]]
    received = utc(clock())
    if received < now:
        raise ValueError("RECEIPT_BEFORE_REQUEST")
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / "raw_aggregates.json"
    raw_path.write_text(json.dumps(raw_by_contract, sort_keys=True, allow_nan=False))
    rows, seen = [], set()
    for ticker, raw in raw_by_contract.items():
        for row in raw:
            ns = int(row["window_start"])
            key = (ticker, ns)
            if key in seen:
                raise ValueError("DUPLICATE_PROVIDER_BAR")
            seen.add(key)
            if ns % 60_000_000_000:
                raise ValueError("UNALIGNED_PROVIDER_BAR")
            start = datetime.fromtimestamp(ns // 1_000_000_000, timezone.utc)
            if start + MINUTE > now:
                continue  # Freeze signal information at acquisition start.
            rows.append({
                "instrument": "GC", "contract": ticker, "event_time": start.isoformat(),
                "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"],
                "volume": row.get("volume"), "quality_state": "VERIFIED",
                "source_id": f"massive:{ticker}:{ns}", "roll_method": "RAW_CONTRACT", "is_roll_window": False,
            })
    rows.sort(key=lambda r: (r["contract"], r["event_time"]))
    bars_path = output / "bars.jsonl"
    bars_path.write_text("".join(json.dumps(r, sort_keys=True, allow_nan=False) + "\n" for r in rows))
    if not rows:
        raise ValueError("NO_CLOSED_BARS")
    index_bars(load_bars(bars_path), received)  # Validate prices/volume before metadata attestation.
    meta = {
        "experiment_id": EXPERIMENT, "request_started_at": now.isoformat(),
        "received_at": received.isoformat(), "contract": contract, "requested_contracts": contracts,
        "front_selection_session": selection_session, "front_selection_volume": selection_volume,
        "snapshot_hash": sha256(bars_path.read_bytes()).hexdigest(),
        "raw_hash": sha256(raw_path.read_bytes()).hexdigest(), "bars": len(rows),
        "quality_scope": "SCHEMA_OHLC_VOLUME_VALIDATED_NOT_INDEPENDENT_MARKET_VERIFICATION",
        "real_orders_allowed": False,
    }
    (output / "acquisition.json").write_text(json.dumps(meta, sort_keys=True, indent=2))
    return meta


def run_cycle(*, ledger, bars_path, metadata, engine_commit, clock=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    if sha256(bars_path.read_bytes()).hexdigest() != metadata["snapshot_hash"]:
        raise ValueError("SNAPSHOT_HASH_MISMATCH")
    bars = load_bars(bars_path)
    received = utc(metadata["received_at"])
    closed = index_bars(bars, received)
    structural = build_windows(tuple(b for (c, _), b in closed.items() if c == metadata["contract"]))
    appended = settle(ledger=ledger, bars=bars, received_at=received, snapshot_hash=metadata["snapshot_hash"])
    # Sample actual wall clock AFTER feature extraction and prior settlement.
    decision_at = utc(clock())
    latest = structural["candidates"][-1] if structural["candidates"] else None
    record = record_decision(
        ledger=ledger, candidate=latest, bars=bars, front_contract=metadata["contract"],
        received_at=received, decision_at=decision_at, snapshot_hash=metadata["snapshot_hash"],
        engine_commit=engine_commit, candidate_hash=structural["candidate_windows_hash"], commit_clock=clock,
    )
    return {"experiment_id": EXPERIMENT, "scope": "ENGINEERING_ONLY",
            "action": record["payload"]["action"], "reason": record["payload"]["reason"],
            "settlement_records": appended, "ledger_sequence": record["seq"],
            "ledger_tip": record["record_hash"], "formal_verdict_allowed": False,
            "real_orders_allowed": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--engine-commit", required=True)
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args()
    if os.environ.get("LIVE_ORDER_ALLOWED", "false").lower() != "false":
        raise RuntimeError("LIVE_ORDERS_FORBIDDEN")
    ledger = HashChainLedger(args.ledger)
    if args.initialize:
        ledger.path.parent.mkdir(parents=True, exist_ok=True)
        with ledger.path.open("x"):
            pass  # Exclusive create: never erase an existing ledger.
        ledger.append("GENESIS", {"experiment_id": EXPERIMENT, "scope": "ENGINEERING_ONLY"})
    elif not ledger.path.exists() or not ledger.read_verified():
        raise ValueError("MISSING_LEDGER_EXPLICIT_INITIALIZATION_REQUIRED")
    output = Path(args.output_dir)
    metadata = collect(Massive(os.environ.get("MASSIVE_API_KEY", "")), ledger,
                       datetime.now(timezone.utc), output)
    summary = run_cycle(ledger=ledger, bars_path=output / "bars.jsonl", metadata=metadata,
                        engine_commit=args.engine_commit)
    (output / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2))
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
