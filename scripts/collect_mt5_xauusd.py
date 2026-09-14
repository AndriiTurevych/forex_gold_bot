#!/usr/bin/env python3
"""Collect one outcome-free XAUUSD quote/M1 snapshot from a local MT5 terminal."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from gold_cio_v9.data.mt5_snapshot import SCHEMA, seal


def _value(record: Any, name: str, default: Any = None) -> Any:
    return getattr(record, name, default)


def collect(mt5: Any, *, symbol: str, bar_count: int, terminal_path: str | None = None) -> dict:
    if bar_count < 120:
        raise ValueError("bar_count must be at least 120")
    initialized = mt5.initialize(terminal_path) if terminal_path else mt5.initialize()
    if not initialized:
        raise RuntimeError(f"MT5_INITIALIZE_FAILED:{mt5.last_error()}")
    try:
        terminal = mt5.terminal_info()
        if terminal is None or not bool(_value(terminal, "connected", False)):
            raise RuntimeError("MT5_NOT_CONNECTED")
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"MT5_SYMBOL_SELECT_FAILED:{symbol}")
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, bar_count)
        if info is None or tick is None:
            raise RuntimeError("MT5_SYMBOL_OR_TICK_UNAVAILABLE")
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"MT5_RATES_UNAVAILABLE:{mt5.last_error()}")
        acquired_at = datetime.now(timezone.utc)
        bars = []
        for row in sorted(rates, key=lambda value: int(value["time"])):
            start = datetime.fromtimestamp(int(row["time"]), tz=timezone.utc)
            if start + timedelta(minutes=1) > acquired_at:
                continue
            bars.append({
                "event_time": start.isoformat(),
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "tick_volume": int(row["tick_volume"]),
                "spread_points": int(row["spread"]),
                "real_volume": int(row["real_volume"]),
            })
        event_msc = int(_value(tick, "time_msc", 0))
        event_time = (datetime.fromtimestamp(event_msc / 1000, tz=timezone.utc)
                      if event_msc > 0 else datetime.fromtimestamp(int(tick.time), tz=timezone.utc))
        payload = {
            "schema": SCHEMA,
            "source": "MT5_BROKER_TERMINAL",
            "purpose": "OUTCOME_FREE_BROKER_FEED_PREFLIGHT",
            "acquired_at": acquired_at.isoformat(),
            "instrument": {
                "symbol": symbol,
                "digits": int(_value(info, "digits", 0)),
                "point": float(_value(info, "point", 0)),
                "trade_tick_size": float(_value(info, "trade_tick_size", 0)),
                "trade_contract_size": float(_value(info, "trade_contract_size", 0)),
                "volume_min": float(_value(info, "volume_min", 0)),
                "volume_max": float(_value(info, "volume_max", 0)),
                "volume_step": float(_value(info, "volume_step", 0)),
                "currency_profit": str(_value(info, "currency_profit", "")),
            },
            "quote": {
                "event_time": event_time.isoformat(),
                "bid": float(tick.bid), "ask": float(tick.ask),
                "last": float(_value(tick, "last", 0)),
                "volume": float(_value(tick, "volume_real", _value(tick, "volume", 0))),
                "flags": int(_value(tick, "flags", 0)),
            },
            "timeframe": "M1_CLOSED_ONLY",
            "m1_bars": bars,
            "identity_redaction": "NO_ACCOUNT_LOGIN_NO_ACCOUNT_NAME_NO_SERVER",
            "instrument_separation": "BROKER_XAUUSD_NOT_COMEX_GC",
            "real_orders_allowed": False,
        }
        return seal(payload)
    finally:
        mt5.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--bars", type=int, default=2880)
    parser.add_argument("--terminal-path")
    args = parser.parse_args()
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError("MetaTrader5 package is required on the Windows MT5 host") from exc
    payload = collect(mt5, symbol=args.symbol, bar_count=args.bars, terminal_path=args.terminal_path)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({
        "symbol": payload["instrument"]["symbol"],
        "bars": len(payload["m1_bars"]),
        "quote_time": payload["quote"]["event_time"],
        "snapshot_hash": payload["snapshot_hash"],
        "real_orders_allowed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
