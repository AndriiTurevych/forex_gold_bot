"""Fail-closed MT5 demo executor and local position protection for MIDAS v2.

This module refuses real accounts by checking MT5 account trade_mode against
ACCOUNT_TRADE_MODE_DEMO. It also requires an explicit environment switch.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any


EXECUTION_SCHEMA = "midas-mt5-demo-execution-v1"
DEFAULT_MAGIC = 56002026


def _enabled() -> bool:
    return os.environ.get("MIDAS_DEMO_EXECUTION_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def _decision_key(decision: dict[str, Any]) -> str:
    selected = {
        "symbol": decision.get("symbol"),
        "decision_time": decision.get("decision_time"),
        "final_action": decision.get("final_action"),
        "entry": decision.get("entry"),
        "stop": decision.get("stop"),
        "tp2": decision.get("tp2"),
        "proposed_volume_lots": decision.get("proposed_volume_lots"),
    }
    return sha256(json.dumps(selected, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def _base(status: str, reason: str) -> dict[str, Any]:
    return {
        "schema": EXECUTION_SCHEMA,
        "status": status,
        "reason": reason,
        "order_sent": False,
        "position_managed": False,
        "real_orders_allowed": False,
    }


def _assert_demo_account(mt5: Any) -> tuple[Any | None, str | None]:
    account = mt5.account_info()
    if account is None:
        return None, "MT5_ACCOUNT_INFO_UNAVAILABLE"
    demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
    if getattr(account, "trade_mode", None) != demo_mode:
        return None, "REAL_OR_NONDEMO_ACCOUNT_BLOCKED"
    if not bool(getattr(account, "trade_allowed", False)):
        return None, "MT5_TRADE_NOT_ALLOWED"
    if not bool(getattr(account, "trade_expert", False)):
        return None, "MT5_EXPERT_TRADING_NOT_ALLOWED"
    return account, None


def manage_demo_position(mt5: Any, *, state_path: str | Path) -> dict[str, Any]:
    """Move SL to breakeven after TP1. Broker-side TP2 remains the final exit."""
    result = _base("SKIPPED", "NO_ACTIVE_MIDAS_DEMO_POSITION")
    if not _enabled():
        return _base("DISABLED", "MIDAS_DEMO_EXECUTION_DISABLED")

    _, error = _assert_demo_account(mt5)
    if error:
        return _base("BLOCKED", error)

    path = Path(state_path)
    state = _read_state(path)
    if not state.get("active"):
        return result

    symbol = str(state.get("symbol") or "")
    magic = int(state.get("magic") or DEFAULT_MAGIC)
    positions = mt5.positions_get(symbol=symbol) or ()
    position = next((p for p in positions if int(getattr(p, "magic", -1)) == magic), None)
    if position is None:
        state["active"] = False
        state["closed_detected"] = True
        _write_state(path, state)
        return _base("OK", "POSITION_ALREADY_CLOSED")

    if state.get("breakeven_moved"):
        return _base("OK", "BREAKEVEN_ALREADY_SET")

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return _base("BLOCKED", "MT5_TICK_UNAVAILABLE")

    action = str(state.get("action") or "")
    entry = float(state["entry"])
    tp1 = float(state["tp1"])
    tp2 = float(state["tp2"])
    market_price = float(tick.bid if action == "BUY" else tick.ask)
    reached = market_price >= tp1 if action == "BUY" else market_price <= tp1
    if not reached:
        return _base("OK", "TP1_NOT_REACHED")

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": int(getattr(position, "ticket")),
        "sl": entry,
        "tp": tp2,
        "magic": magic,
    }
    response = mt5.order_send(request)
    if response is None:
        return _base("ERROR", "MT5_SLTP_NO_RESPONSE")
    if int(getattr(response, "retcode", -1)) != int(getattr(mt5, "TRADE_RETCODE_DONE")):
        blocked = _base("ERROR", f"MT5_SLTP_RETCODE_{getattr(response, 'retcode', 'UNKNOWN')}")
        return blocked

    state["breakeven_moved"] = True
    state["breakeven_price"] = entry
    _write_state(path, state)
    managed = _base("OK", "STOP_MOVED_TO_BREAKEVEN")
    managed["position_managed"] = True
    managed["position_ticket"] = int(getattr(position, "ticket"))
    return managed


def execute_demo_decision(mt5: Any, decision: dict[str, Any], *, state_path: str | Path) -> dict[str, Any]:
    """Execute at most one market entry for an approved MIDAS demo decision."""
    if not _enabled():
        return _base("DISABLED", "MIDAS_DEMO_EXECUTION_DISABLED")
    if decision.get("real_orders_allowed") is not False:
        return _base("BLOCKED", "DECISION_REAL_ORDER_INVARIANT_FAILED")
    if decision.get("execution_allowed") is not False:
        return _base("BLOCKED", "REAL_EXECUTION_FLAG_MUST_REMAIN_FALSE")
    if not bool(decision.get("demo_execution_allowed")):
        return _base("SKIPPED", "NO_APPROVED_DEMO_DECISION")
    if decision.get("final_action") not in {"BUY", "SELL"}:
        return _base("BLOCKED", "INVALID_FINAL_ACTION")

    _, error = _assert_demo_account(mt5)
    if error:
        return _base("BLOCKED", error)

    symbol = str(decision.get("symbol") or "").strip()
    if not symbol:
        return _base("BLOCKED", "SYMBOL_MISSING")
    if not mt5.symbol_select(symbol, True):
        return _base("BLOCKED", "SYMBOL_SELECT_FAILED")

    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if info is None or tick is None:
        return _base("BLOCKED", "SYMBOL_INFO_OR_TICK_UNAVAILABLE")

    point = float(getattr(info, "point", 0.0) or 0.0)
    if point <= 0:
        return _base("BLOCKED", "INVALID_SYMBOL_POINT")

    action = str(decision["final_action"])
    intended_entry = float(decision["entry"])
    current_price = float(tick.ask if action == "BUY" else tick.bid)
    max_slippage_points = float(os.environ.get("MIDAS_MAX_ENTRY_DRIFT_POINTS", "50"))
    drift_points = abs(current_price - intended_entry) / point
    if drift_points > max_slippage_points:
        blocked = _base("BLOCKED", "ENTRY_DRIFT_LIMIT")
        blocked["entry_drift_points"] = round(drift_points, 2)
        return blocked

    volume = float(decision.get("proposed_volume_lots") or 0.0)
    minimum = float(getattr(info, "volume_min", 0.0) or 0.0)
    maximum = float(getattr(info, "volume_max", 0.0) or 0.0)
    if volume <= 0 or volume < minimum or (maximum > 0 and volume > maximum):
        return _base("BLOCKED", "INVALID_DEMO_VOLUME")

    stop = float(decision["stop"])
    tp1 = float(decision["tp1"])
    tp2 = float(decision["tp2"])
    if action == "BUY" and not (stop < current_price < tp1 < tp2):
        return _base("BLOCKED", "INVALID_BUY_EXECUTION_GEOMETRY")
    if action == "SELL" and not (tp2 < tp1 < current_price < stop):
        return _base("BLOCKED", "INVALID_SELL_EXECUTION_GEOMETRY")

    magic = int(os.environ.get("MIDAS_MT5_MAGIC", str(DEFAULT_MAGIC)))
    positions = mt5.positions_get(symbol=symbol) or ()
    if any(int(getattr(p, "magic", -1)) == magic for p in positions):
        return _base("SKIPPED", "MIDAS_POSITION_ALREADY_OPEN")

    path = Path(state_path)
    state = _read_state(path)
    key = _decision_key(decision)
    if state.get("last_executed_decision_key") == key:
        return _base("SKIPPED", "DUPLICATE_DECISION")

    order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
    deviation = int(os.environ.get("MIDAS_MT5_DEVIATION_POINTS", "30"))
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": current_price,
        "sl": stop,
        "tp": tp2,
        "deviation": deviation,
        "magic": magic,
        "comment": "MIDAS_V2_DEMO",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": int(getattr(info, "filling_mode")),
    }
    response = mt5.order_send(request)
    if response is None:
        return _base("ERROR", "MT5_ORDER_NO_RESPONSE")

    retcode = int(getattr(response, "retcode", -1))
    accepted = {
        int(getattr(mt5, "TRADE_RETCODE_DONE")),
        int(getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", getattr(mt5, "TRADE_RETCODE_DONE"))),
    }
    if retcode not in accepted:
        failed = _base("ERROR", f"MT5_ORDER_RETCODE_{retcode}")
        failed["retcode"] = retcode
        return failed

    new_state = {
        "schema": EXECUTION_SCHEMA,
        "active": True,
        "last_executed_decision_key": key,
        "symbol": symbol,
        "action": action,
        "entry": current_price,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "volume": volume,
        "magic": magic,
        "order_ticket": int(getattr(response, "order", 0) or 0),
        "deal_ticket": int(getattr(response, "deal", 0) or 0),
        "breakeven_moved": False,
        "real_orders_allowed": False,
    }
    _write_state(path, new_state)

    ok = _base("OK", "DEMO_ORDER_ACCEPTED")
    ok["order_sent"] = True
    ok["action"] = action
    ok["symbol"] = symbol
    ok["volume"] = volume
    ok["entry"] = current_price
    ok["stop"] = stop
    ok["tp2"] = tp2
    ok["order_ticket"] = new_state["order_ticket"]
    ok["deal_ticket"] = new_state["deal_ticket"]
    ok["retcode"] = retcode
    return ok
