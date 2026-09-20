"""Read privacy-minimized MT5 account state for MIDAS risk controls.

No login, account name or broker server is persisted. Only execution-relevant
state is returned: equity/balance, demo mode, MIDAS daily P/L, losing streak and
MIDAS open-position count.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
import os
from typing import Any


ACCOUNT_STATE_SCHEMA = "midas-mt5-account-state-v1"


def _enabled_env(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in {"1", "true", "yes", "on"}


def execution_backend_enabled() -> bool:
    return _enabled_env("MIDAS_EA_COMMAND_ENABLED") or _enabled_env("MIDAS_DEMO_EXECUTION_ENABLED")


def collect_account_state(
    mt5: Any,
    *,
    terminal_path: str | None,
    server_utc_offset_hours: float = 0.0,
    mt5_timeout_ms: int = 10_000,
    magic: int | None = None,
) -> dict[str, Any]:
    magic = magic if magic is not None else int(os.environ.get("MIDAS_MT5_MAGIC", "56002026"))
    initialized = (
        mt5.initialize(terminal_path, timeout=mt5_timeout_ms)
        if terminal_path
        else mt5.initialize(timeout=mt5_timeout_ms)
    )
    if not initialized:
        raise RuntimeError(f"MT5_INITIALIZE_FAILED:{mt5.last_error()}")
    try:
        account = mt5.account_info()
        if account is None:
            raise RuntimeError("MT5_ACCOUNT_INFO_UNAVAILABLE")

        equity = float(getattr(account, "equity", 0.0) or 0.0)
        balance = float(getattr(account, "balance", 0.0) or 0.0)
        if not (isfinite(equity) and isfinite(balance) and equity > 0 and balance > 0):
            raise RuntimeError("MT5_ACCOUNT_EQUITY_OR_BALANCE_INVALID")

        trade_mode = int(getattr(account, "trade_mode", -1))
        demo_mode = int(getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0))
        contest_mode = int(getattr(mt5, "ACCOUNT_TRADE_MODE_CONTEST", 1))
        mode_name = "DEMO" if trade_mode == demo_mode else "CONTEST" if trade_mode == contest_mode else "REAL_OR_OTHER"

        positions = tuple(mt5.positions_get() or ())
        midas_positions = [p for p in positions if int(getattr(p, "magic", -1)) == magic]

        now_utc = datetime.now(timezone.utc)
        offset = timedelta(hours=server_utc_offset_hours)
        broker_now = now_utc + offset
        broker_start = broker_now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = broker_start - offset

        deals = tuple(mt5.history_deals_get(start_utc, now_utc) or ())
        closing_entries = {
            int(getattr(mt5, "DEAL_ENTRY_OUT", 1)),
            int(getattr(mt5, "DEAL_ENTRY_OUT_BY", 3)),
        }
        closed = []
        for deal in deals:
            if int(getattr(deal, "magic", -1)) != magic:
                continue
            if int(getattr(deal, "entry", -1)) not in closing_entries:
                continue
            net = sum(float(getattr(deal, field, 0.0) or 0.0) for field in ("profit", "commission", "swap", "fee"))
            closed.append((int(getattr(deal, "time_msc", 0) or 0), net))

        daily_net = sum(net for _, net in closed)
        start_balance = balance - daily_net
        daily_loss_fraction = max(0.0, -daily_net / start_balance) if start_balance > 0 else 0.0

        consecutive_losses = 0
        for _, net in sorted(closed, reverse=True):
            if net < 0:
                consecutive_losses += 1
            else:
                break

        return {
            "schema": ACCOUNT_STATE_SCHEMA,
            "observed_at": now_utc.isoformat(),
            "trade_mode": mode_name,
            "demo_account": trade_mode == demo_mode,
            "trade_allowed": bool(getattr(account, "trade_allowed", False)),
            "trade_expert": bool(getattr(account, "trade_expert", False)),
            "equity": round(equity, 2),
            "balance": round(balance, 2),
            "daily_realized_pnl": round(daily_net, 2),
            "daily_loss_fraction": round(daily_loss_fraction, 8),
            "consecutive_losses": consecutive_losses,
            "open_positions": len(midas_positions),
            "magic": magic,
            "identity_redaction": "NO_LOGIN_NO_ACCOUNT_NAME_NO_SERVER",
            "real_orders_allowed": False,
        }
    finally:
        mt5.shutdown()
