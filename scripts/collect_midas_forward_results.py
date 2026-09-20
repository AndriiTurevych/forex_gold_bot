#!/usr/bin/env python3
"""Refresh the local resolved-trade ledger from MIDAS EA events."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gold_cio_v9.live.forward_results import collect_resolved_trades, write_resolved_csv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terminal-path", required=True)
    parser.add_argument("--output", default="mt5_artifacts/resolved_trades.csv")
    parser.add_argument("--mt5-timeout-ms", type=int, default=10_000)
    args = parser.parse_args()

    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError("MetaTrader5 package is required on the Windows MT5 host") from exc

    rows = collect_resolved_trades(
        mt5,
        terminal_path=args.terminal_path,
        mt5_timeout_ms=args.mt5_timeout_ms,
    )
    write_resolved_csv(args.output, rows)
    print(json.dumps({
        "ok": True,
        "resolved_trades": len(rows),
        "output": str(Path(args.output)),
        "real_orders_allowed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
