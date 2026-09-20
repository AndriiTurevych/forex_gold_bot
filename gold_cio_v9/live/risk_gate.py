"""Deterministic risk gate for MIDAS shadow/demo execution.

This module is intentionally independent of model output beyond the three-state
AI decision and an allowed risk-reduction multiplier. It never enables real orders.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import isfinite
import os
from typing import Any


RISK_GATE_SCHEMA = "midas-risk-gate-v1"


@dataclass(frozen=True)
class RiskLimits:
    max_risk_fraction: float = 0.0025
    max_spread_points: float = 80.0
    min_rr_to_tp2: float = 1.8
    max_daily_loss_fraction: float = 0.01
    max_consecutive_losses: int = 3
    max_open_positions: int = 1

    @classmethod
    def from_env(cls) -> "RiskLimits":
        return cls(
            max_risk_fraction=float(os.environ.get("MIDAS_MAX_RISK_FRACTION", "0.0025")),
            max_spread_points=float(os.environ.get("MIDAS_MAX_SPREAD_POINTS", "80")),
            min_rr_to_tp2=float(os.environ.get("MIDAS_MIN_RR_TP2", "1.8")),
            max_daily_loss_fraction=float(os.environ.get("MIDAS_MAX_DAILY_LOSS_FRACTION", "0.01")),
            max_consecutive_losses=int(os.environ.get("MIDAS_MAX_CONSECUTIVE_LOSSES", "3")),
            max_open_positions=int(os.environ.get("MIDAS_MAX_OPEN_POSITIONS", "1")),
        )


def evaluate_risk(
    snapshot: dict[str, Any],
    analysis: dict[str, Any],
    ai_gate: dict[str, Any],
    *,
    account_state: dict[str, Any] | None = None,
    limits: RiskLimits | None = None,
) -> dict[str, Any]:
    limits = limits or RiskLimits.from_env()
    reasons: list[str] = []

    if analysis.get("state") != "CONFIRMED" or analysis.get("action") not in {"BUY", "SELL"}:
        reasons.append("NO_CONFIRMED_CANDIDATE")

    ai_decision = ai_gate.get("decision")
    if ai_decision not in {"ALLOW", "REDUCE_RISK"}:
        reasons.append("AI_GATE_BLOCK")

    try:
        risk_fraction = float(analysis.get("risk_fraction"))
    except (TypeError, ValueError):
        risk_fraction = float("nan")
    if not isfinite(risk_fraction) or risk_fraction <= 0 or risk_fraction > limits.max_risk_fraction:
        reasons.append("RISK_FRACTION_LIMIT")

    entry = analysis.get("entry")
    stop = analysis.get("stop")
    tp2 = analysis.get("tp2")
    rr_to_tp2 = None
    try:
        entry_f, stop_f, tp2_f = float(entry), float(stop), float(tp2)
        risk_distance = abs(entry_f - stop_f)
        reward_distance = abs(tp2_f - entry_f)
        if risk_distance <= 0:
            reasons.append("INVALID_STOP_DISTANCE")
        else:
            rr_to_tp2 = reward_distance / risk_distance
            if rr_to_tp2 < limits.min_rr_to_tp2:
                reasons.append("RR_BELOW_MINIMUM")
        if analysis.get("action") == "BUY" and not (stop_f < entry_f < tp2_f):
            reasons.append("INVALID_BUY_GEOMETRY")
        if analysis.get("action") == "SELL" and not (tp2_f < entry_f < stop_f):
            reasons.append("INVALID_SELL_GEOMETRY")
    except (TypeError, ValueError):
        reasons.append("INVALID_LEVELS")

    instrument = snapshot.get("instrument") or {}
    quote = snapshot.get("quote") or {}
    try:
        point = float(instrument.get("point"))
        bid = float(quote.get("bid"))
        ask = float(quote.get("ask"))
        spread_points = (ask - bid) / point
        if point <= 0 or spread_points < 0 or spread_points > limits.max_spread_points:
            reasons.append("SPREAD_LIMIT")
    except (TypeError, ValueError, ZeroDivisionError):
        spread_points = None
        reasons.append("SPREAD_UNKNOWN")

    account_state = account_state or {}
    if account_state:
        daily_loss = float(account_state.get("daily_loss_fraction", 0.0) or 0.0)
        consecutive_losses = int(account_state.get("consecutive_losses", 0) or 0)
        open_positions = int(account_state.get("open_positions", 0) or 0)
        if daily_loss >= limits.max_daily_loss_fraction:
            reasons.append("DAILY_LOSS_LIMIT")
        if consecutive_losses >= limits.max_consecutive_losses:
            reasons.append("CONSECUTIVE_LOSS_LIMIT")
        if open_positions >= limits.max_open_positions:
            reasons.append("OPEN_POSITION_LIMIT")

    multiplier = float(ai_gate.get("risk_multiplier") or 0.0)
    if ai_decision == "ALLOW":
        multiplier = 1.0
    elif ai_decision == "REDUCE_RISK":
        if multiplier not in {0.25, 0.5, 0.75}:
            reasons.append("INVALID_AI_RISK_MULTIPLIER")
    else:
        multiplier = 0.0

    approved = not reasons
    effective_risk_fraction = risk_fraction * multiplier if approved and isfinite(risk_fraction) else 0.0

    return {
        "schema": RISK_GATE_SCHEMA,
        "approved": approved,
        "demo_execution_allowed": approved,
        "execution_allowed": False,
        "real_orders_allowed": False,
        "action": analysis.get("action") if approved else "ABSTAIN",
        "effective_risk_fraction": round(effective_risk_fraction, 8),
        "risk_multiplier": multiplier if approved else 0.0,
        "rr_to_tp2": round(rr_to_tp2, 4) if rr_to_tp2 is not None else None,
        "spread_points": round(spread_points, 2) if spread_points is not None else None,
        "reasons": reasons or ["APPROVED_FOR_DEMO_ONLY"],
        "limits": asdict(limits),
    }
