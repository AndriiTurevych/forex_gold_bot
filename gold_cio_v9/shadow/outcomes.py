"""Append matured shadow outcomes without mutating original decisions."""
from __future__ import annotations

from datetime import datetime, timedelta

from gold_cio_v9.data.governance import HistoricalBar
from gold_cio_v9.shadow.ledger import HashChainLedger


HORIZONS_MINUTES = (5, 15, 30, 60)
ROUND_TRIP_COST_PRICE = 0.35


def settle_matured(ledger: HashChainLedger, bars: tuple[HistoricalBar, ...]) -> int:
    rows = ledger.read_verified()
    completed = {
        (row["payload"]["signal_id"], row["payload"]["horizon_minutes"])
        for row in rows if row["event_type"] == "OUTCOME"
    }
    appended = 0
    for row in rows:
        if row["event_type"] != "DECISION" or row["payload"].get("action") not in {"BUY", "SELL"}:
            continue
        p = row["payload"]
        decision_time = datetime.fromisoformat(p["decision_time"])
        for horizon in HORIZONS_MINUTES:
            key = (p["signal_id"], horizon)
            if key in completed:
                continue
            maturity = decision_time + timedelta(minutes=horizon)
            eligible = [b for b in bars if b.contract == p["contract"] and b.event_time >= maturity]
            if not eligible:
                continue
            exit_bar = min(eligible, key=lambda b: b.event_time)
            sign = 1.0 if p["action"] == "BUY" else -1.0
            gross = sign * (exit_bar.close - float(p["entry_price"]))
            ledger.append("OUTCOME", {
                "signal_id": p["signal_id"], "horizon_minutes": horizon,
                "maturity_time": maturity.isoformat(), "exit_time": exit_bar.event_time.isoformat(),
                "exit_price": exit_bar.close, "gross_pnl_price": gross,
                "net_pnl_price": gross - ROUND_TRIP_COST_PRICE,
            })
            completed.add(key)
            appended += 1
    return appended
