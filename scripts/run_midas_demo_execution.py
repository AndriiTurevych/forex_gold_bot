#!/usr/bin/env python3
"""Run one MIDAS v2 demo-execution/position-management cycle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gold_cio_v9.live.demo_execution import execute_demo_decision, manage_demo_position


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terminal-path", required=True)
    parser.add_argument("--decision", default="mt5_artifacts/decision.json")
    parser.add_argument("--state", default="mt5_artifacts/demo_position_state.json")
    parser.add_argument("--output", default="mt5_artifacts/demo_execution.json")
    parser.add_argument("--mt5-timeout-ms", type=int, default=10_000)
    args = parser.parse_args()

    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError("MetaTrader5 package is required on the Windows MT5 host") from exc

    decision_path = Path(args.decision)
    if not decision_path.exists():
        raise RuntimeError(f"DECISION_FILE_NOT_FOUND:{decision_path}")
    decision = json.loads(decision_path.read_text(encoding="utf-8"))

    initialized = mt5.initialize(path=args.terminal_path, timeout=args.mt5_timeout_ms)
    if not initialized:
        raise RuntimeError(f"MT5_INITIALIZE_FAILED:{mt5.last_error()}")
    try:
        management = manage_demo_position(mt5, state_path=args.state)
        execution = execute_demo_decision(mt5, decision, state_path=args.state)
        payload = {
            "ok": execution.get("status") not in {"ERROR"},
            "management": management,
            "execution": execution,
            "real_orders_allowed": False,
        }
        _atomic_json(Path(args.output), payload)
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload["ok"] else 1
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
