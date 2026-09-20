"""Publish a fail-closed MIDAS v2 command/dashboard row for the MT5 EA."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import csv
import os
from pathlib import Path
from typing import Any


EA_COMMAND_SCHEMA = "MIDAS_V2_EA_2"
EA_COMMAND_RELATIVE_PATH = Path("MIDAS") / "midas_command.csv"


def _enabled() -> bool:
    return os.environ.get("MIDAS_EA_COMMAND_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def _utc(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("NAIVE_DECISION_TIME")
    return parsed.astimezone(timezone.utc)


def _decision_id(decision: dict[str, Any]) -> int:
    signal_id = str(decision.get("signal_id") or "").strip()
    if signal_id:
        material = f"{signal_id}|{decision.get('final_action') or 'ABSTAIN'}"
    else:
        material = "|".join(
            str(decision.get(key) or "")
            for key in ("symbol", "decision_time", "final_action", "entry", "stop", "tp2")
        )
    # 52 bits are exactly representable in an MQL5 GlobalVariable double.
    return int(sha256(material.encode("utf-8")).hexdigest()[:13], 16)


def _command(decision: dict[str, Any], *, ttl_seconds: int) -> dict[str, Any]:
    approved = bool(decision.get("demo_execution_allowed"))
    action = str(decision.get("final_action") or "ABSTAIN").upper()
    if not approved or action not in {"BUY", "SELL"}:
        action = "ABSTAIN"

    decision_time = _utc(decision.get("decision_time"))
    expires = max(datetime.now(timezone.utc), decision_time) + timedelta(seconds=ttl_seconds)
    risk = decision.get("risk_gate") or {}
    limits = risk.get("limits") or {}
    ai = decision.get("ai_gate") or {}

    return {
        "schema": EA_COMMAND_SCHEMA,
        "decision_id": _decision_id(decision),
        "signal_id": str(decision.get("signal_id") or ""),
        "symbol": str(decision.get("symbol") or "XAUUSD").upper(),
        "action": action,
        "mode": str(ai.get("regime") or "UNKNOWN"),
        "strategy": str(decision.get("strategy") or "CRT_TBS"),
        "setup_model": str(decision.get("setup_model") or "WAIT"),
        "h4_bias": str(decision.get("h4_bias") or "NEUTRAL"),
        "h1_bias": str(decision.get("h1_bias") or "NEUTRAL"),
        "setup": "ARMED" if decision.get("candidate_action") in {"BUY", "SELL"} else "WAIT",
        "ai_gate": str(ai.get("decision") or "BLOCK"),
        "risk_gate": "PASS" if bool(risk.get("approved")) else "BLOCK",
        "confidence": int(decision.get("confidence_score") or 0),
        "risk_pct": 100.0 * float(risk.get("effective_risk_fraction") or 0.0),
        "rr": float(risk.get("rr_to_tp2") or 0.0),
        "spread_points": float(risk.get("spread_points") or 0.0),
        "volume_lots": float(decision.get("proposed_volume_lots") or 0.0) if action != "ABSTAIN" else 0.0,
        "entry": float(decision.get("entry") or 0.0) if action != "ABSTAIN" else 0.0,
        "stop": float(decision.get("stop") or 0.0) if action != "ABSTAIN" else 0.0,
        "tp1": float(decision.get("tp1") or 0.0) if action != "ABSTAIN" else 0.0,
        "tp2": float(decision.get("tp2") or 0.0) if action != "ABSTAIN" else 0.0,
        "max_spread_points": float(limits.get("max_spread_points") or os.environ.get("MIDAS_MAX_SPREAD_POINTS", "80")),
        "max_entry_drift_points": float(os.environ.get("MIDAS_MAX_ENTRY_DRIFT_POINTS", "50")),
        "expires_epoch": int(expires.timestamp()),
        "magic": int(os.environ.get("MIDAS_MT5_MAGIC", "56002026")),
        "real_orders_allowed": 0,
    }


def publish_ea_command(
    mt5: Any,
    decision: dict[str, Any],
    *,
    terminal_path: str | None,
    mt5_timeout_ms: int = 10_000,
    ttl_seconds: int | None = None,
) -> dict[str, Any]:
    if not _enabled():
        return {"published": False, "reason": "MIDAS_EA_COMMAND_DISABLED", "real_orders_allowed": False}

    python_executor_enabled = os.environ.get("MIDAS_DEMO_EXECUTION_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
    if python_executor_enabled:
        raise RuntimeError("EXECUTION_BACKEND_CONFLICT:EA_AND_PYTHON_DEMO_BOTH_ENABLED")

    ttl_seconds = ttl_seconds or int(os.environ.get("MIDAS_EA_COMMAND_TTL_SECONDS", "90"))
    if ttl_seconds < 15 or ttl_seconds > 600:
        raise ValueError("MIDAS_EA_COMMAND_TTL_SECONDS_OUT_OF_RANGE")

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

        command = _command(decision, ttl_seconds=ttl_seconds)
        target = Path(common) / "Files" / EA_COMMAND_RELATIVE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        fields = list(command.keys())
        with temporary.open("w", encoding="ascii", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter=";")
            writer.writeheader()
            writer.writerow(command)
        temporary.replace(target)
        return {
            "published": True,
            "path": str(target),
            "schema": command["schema"],
            "decision_id": command["decision_id"],
            "signal_id": command["signal_id"],
            "action": command["action"],
            "ai_gate": command["ai_gate"],
            "risk_gate": command["risk_gate"],
            "expires_epoch": command["expires_epoch"],
            "real_orders_allowed": False,
        }
    finally:
        mt5.shutdown()
