"""MIDAS v2 decision pipeline: strategy -> AI context -> risk gate.

The output is a demo/shadow decision artifact. Real-order execution remains
hard-disabled here by design.
"""
from __future__ import annotations

from math import floor
from typing import Any

from gold_cio_v9.live.ai_gate import evaluate_context
from gold_cio_v9.live.mt5_analysis import analyze_snapshot
from gold_cio_v9.live.risk_gate import evaluate_risk


DECISION_SCHEMA = "midas-decision-pipeline-v2"


def _adjust_volume(volume: Any, multiplier: float, instrument: dict[str, Any]) -> float | None:
    try:
        raw = float(volume) * float(multiplier)
        minimum = float(instrument.get("volume_min") or 0.01)
        maximum = float(instrument.get("volume_max") or raw)
        step = float(instrument.get("volume_step") or minimum)
    except (TypeError, ValueError):
        return None
    if raw <= 0 or step <= 0:
        return None
    rounded = min(maximum, floor(raw / step + 1e-12) * step)
    return round(rounded, 8) if rounded >= minimum else None


def build_decision(
    snapshot: dict[str, Any],
    *,
    analysis: dict[str, Any] | None = None,
    shadow_equity: float | None = None,
    account_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis = analysis or analyze_snapshot(snapshot, shadow_equity=shadow_equity)
    ai_gate = evaluate_context(snapshot, analysis)
    risk_gate = evaluate_risk(snapshot, analysis, ai_gate, account_state=account_state)

    approved = bool(risk_gate.get("demo_execution_allowed"))
    multiplier = float(risk_gate.get("risk_multiplier") or 0.0)
    proposed_volume = _adjust_volume(
        analysis.get("volume_lots"),
        multiplier,
        snapshot.get("instrument") or {},
    ) if approved else None

    if approved and proposed_volume is None:
        approved = False
        risk_gate = dict(risk_gate)
        risk_gate["approved"] = False
        risk_gate["demo_execution_allowed"] = False
        risk_gate["action"] = "ABSTAIN"
        risk_gate["effective_risk_fraction"] = 0.0
        risk_gate["risk_multiplier"] = 0.0
        risk_gate["reasons"] = list(risk_gate.get("reasons") or []) + ["VOLUME_NOT_SIZED"]

    return {
        "schema": DECISION_SCHEMA,
        "symbol": analysis.get("symbol"),
        "decision_time": analysis.get("decision_time"),
        "candidate_action": analysis.get("action"),
        "final_action": analysis.get("action") if approved else "ABSTAIN",
        "entry": analysis.get("entry") if approved else None,
        "stop": analysis.get("stop") if approved else None,
        "tp1": analysis.get("tp1") if approved else None,
        "tp2": analysis.get("tp2") if approved else None,
        "proposed_volume_lots": proposed_volume if approved else None,
        "ai_gate": ai_gate,
        "risk_gate": risk_gate,
        "demo_execution_allowed": approved,
        "execution_allowed": False,
        "real_orders_allowed": False,
    }
