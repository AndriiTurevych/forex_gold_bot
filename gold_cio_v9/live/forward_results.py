"""Build resolved MIDAS demo trades from the EA's append-only event journal."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


EVENT_RELATIVE_PATH = Path("MIDAS") / "midas_ea_events.csv"


def _event_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="ascii", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def collect_resolved_trades(
    mt5: Any,
    *,
    terminal_path: str | None,
    mt5_timeout_ms: int = 10_000,
) -> list[dict[str, Any]]:
    initialized = (
        mt5.initialize(terminal_path, timeout=mt5_timeout_ms)
        if terminal_path
        else mt5.initialize(timeout=mt5_timeout_ms)
    )
    if not initialized:
        raise RuntimeError(f"MT5_INITIALIZE_FAILED:{mt5.last_error()}")
    try:
        terminal = mt5.terminal_info()
        if terminal is None:
            raise RuntimeError("MT5_TERMINAL_INFO_UNAVAILABLE")
        common = str(getattr(terminal, "commondata_path", "") or "").strip()
        if not common:
            raise RuntimeError("MT5_COMMONDATA_PATH_UNAVAILABLE")
        path = Path(common) / "Files" / EVENT_RELATIVE_PATH

        current_positions = tuple(mt5.positions_get() or ())
        active_ids = {
            int(getattr(p, "identifier", 0) or 0)
            for p in current_positions
            if int(getattr(p, "identifier", 0) or 0) > 0
        }

        events = _event_rows(path)
        opened: dict[int, dict[str, str]] = {}
        closes: dict[int, list[dict[str, str]]] = {}
        for row in events:
            position_id = int(float(row.get("position_id") or 0))
            if position_id <= 0:
                continue
            if row.get("event") == "OPENED":
                opened[position_id] = row
            elif row.get("event") == "CLOSE_DEAL":
                closes.setdefault(position_id, []).append(row)

        resolved: list[dict[str, Any]] = []
        for position_id, entry in opened.items():
            if position_id in active_ids:
                continue
            close_rows = closes.get(position_id) or []
            if not close_rows:
                continue
            risk_cash = abs(float(entry.get("risk_cash") or 0.0))
            if risk_cash <= 0:
                continue
            net_pnl = sum(float(row.get("net_pnl") or 0.0) for row in close_rows)
            close_time = max(int(float(row.get("time") or 0)) for row in close_rows)
            resolved.append({
                "position_id": position_id,
                "signal_id": entry.get("signal_id") or "",
                "decision_id": int(float(entry.get("decision_id") or 0)),
                "symbol": entry.get("symbol") or "",
                "action": entry.get("action") or "",
                "opened_epoch": int(float(entry.get("time") or 0)),
                "closed_epoch": close_time,
                "volume": float(entry.get("volume") or 0.0),
                "entry": float(entry.get("price") or 0.0),
                "stop": float(entry.get("sl") or 0.0),
                "tp1": float(entry.get("tp1") or 0.0),
                "tp2": float(entry.get("tp2") or 0.0),
                "risk_cash": round(risk_cash, 8),
                "net_pnl": round(net_pnl, 8),
                "r_multiple": round(net_pnl / risk_cash, 8),
                "real_orders_allowed": False,
            })
        return sorted(resolved, key=lambda row: (row["closed_epoch"], row["position_id"]))
    finally:
        mt5.shutdown()


def write_resolved_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "position_id","signal_id","decision_id","symbol","action","opened_epoch","closed_epoch",
        "volume","entry","stop","tp1","tp2","risk_cash","net_pnl","r_multiple","real_orders_allowed",
    ]
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
