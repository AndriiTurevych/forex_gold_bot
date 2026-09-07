#!/usr/bin/env python3
"""Run one stateless-recoverable prospective Gold CIO shadow cycle."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from gold_cio_v9.shadow.engine import ShadowCandidate, ShadowFeed, decide_shadow
from gold_cio_v9.shadow.ledger import HashChainLedger
from gold_cio_v9.shadow.outcomes import settle_matured
from scripts.build_exp0002_structural_windows import build_windows, load_bars


STRATEGY_VERSION = "EXP-0003"
STRATEGY_HASH = "c8468763ebcf1c88d830cdf1966ff0f0d3b0a5a0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", required=True)
    parser.add_argument("--acquisition", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--git-commit", required=True)
    args = parser.parse_args()
    bars = load_bars(Path(args.bars))
    acquisition = json.loads(Path(args.acquisition).read_text(encoding="utf-8"))
    acquired_at = datetime.fromisoformat(acquisition["acquired_at"])
    latest_bar_time = datetime.fromisoformat(acquisition["latest_bar_close_time"])
    ledger = HashChainLedger(args.ledger)
    settled = settle_matured(ledger, bars)
    prior = ledger.read_verified()
    seen = {
        row["payload"]["signal_id"] for row in prior
        if row["event_type"] == "DECISION" and row["payload"].get("action") in {"BUY", "SELL"}
    }
    structural = build_windows(bars)
    latest = structural["candidates"][-1] if structural["candidates"] else None
    candidate = None if latest is None else ShadowCandidate(
        latest["candidate_id"].replace("EXP-0002-", "EXP-0003-", 1),
        latest["contract"], latest["direction"], datetime.fromisoformat(latest["structural_signal_time"]),
    )
    feed = ShadowFeed(
        acquired_at, latest_bar_time, float(acquisition["latest_price"]),
        acquisition["data_snapshot_hash"],
    )
    decision = decide_shadow(
        candidate=candidate, feed=feed, strategy_version=STRATEGY_VERSION,
        seen_signal_ids=seen, real_orders_enabled=False,
    )
    payload = {
        "strategy_version": STRATEGY_VERSION, "strategy_hash": STRATEGY_HASH,
        "git_commit": args.git_commit, "decision_time": acquired_at.isoformat(),
        "action": decision.action, "reason": decision.reason, "signal_id": decision.signal_id,
        "contract": decision.contract, "entry_price": decision.entry_price,
        "candidate_time": None if candidate is None else candidate.event_time.isoformat(),
        "data_snapshot_hash": feed.data_snapshot_hash,
        "candidate_windows_hash": structural["candidate_windows_hash"],
        "feed_age_minutes": (feed.acquired_at - feed.latest_bar_time).total_seconds() / 60,
        "execution_allowed": False, "live_order_attempted": False,
    }
    record = ledger.append("DECISION", payload)
    summary = {
        "action": decision.action, "reason": decision.reason,
        "signal_id": decision.signal_id, "contract": decision.contract,
        "entry_price": decision.entry_price, "settled_outcomes": settled,
        "ledger_sequence": record["seq"], "ledger_tip_hash": record["record_hash"],
        "strategy_outcomes_generated": settled > 0, "real_orders_enabled": False,
    }
    Path(args.summary).write_text(json.dumps(summary, sort_keys=True, indent=2), encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
