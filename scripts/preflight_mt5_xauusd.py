#!/usr/bin/env python3
"""Validate a sealed MT5 XAUUSD snapshot without producing strategy outcomes."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from gold_cio_v9.data.mt5_snapshot import load_snapshot, validate_snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--observed-at")
    parser.add_argument("--max-quote-age-seconds", type=float, default=10.0)
    parser.add_argument("--max-bar-age-minutes", type=float, default=20.0)
    parser.add_argument("--max-spread-price", type=float, default=2.0)
    parser.add_argument("--fail-on-not-ready", action="store_true")
    args = parser.parse_args()
    observed = (datetime.fromisoformat(args.observed_at) if args.observed_at
                else datetime.now(timezone.utc))
    result = validate_snapshot(
        load_snapshot(args.snapshot), observed_at=observed,
        expected_symbol=args.symbol,
        max_quote_age=timedelta(seconds=args.max_quote_age_seconds),
        max_bar_age=timedelta(minutes=args.max_bar_age_minutes),
        max_spread_price=args.max_spread_price,
    ).as_dict()
    result.update({
        "observed_at": observed.astimezone(timezone.utc).isoformat(),
        "purpose": "OUTCOME_FREE_BROKER_FEED_PREFLIGHT",
        "comex_exp0004_data_ready": False,
        "comex_exp0004_reason": "BROKER_XAUUSD_CANNOT_REPLACE_COMEX_GC",
        "strategy_outcomes_computed": False,
    })
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True, indent=2), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 2 if args.fail_on_not_ready and not result["broker_feed_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

