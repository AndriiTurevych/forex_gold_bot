"""Fail-closed OpenAI context gate for MIDAS candidate trades.

The AI gate never creates trades, changes entry/stop/targets, or sizes positions.
It can only ALLOW, REDUCE_RISK, or BLOCK a deterministic candidate produced by
the local strategy engine. Any API/config/parse failure resolves to BLOCK.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


AI_GATE_SCHEMA = "midas-ai-context-gate-v1"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.6-sol"


@dataclass(frozen=True)
class AIGateResult:
    schema: str
    status: str
    decision: str
    context_score: float
    regime: str
    conflict: bool
    risk_multiplier: float
    reason_code: str
    model: str | None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _blocked(status: str, reason_code: str, *, model: str | None = None, error: str | None = None) -> dict[str, Any]:
    return AIGateResult(
        schema=AI_GATE_SCHEMA,
        status=status,
        decision="BLOCK",
        context_score=0.0,
        regime="UNKNOWN",
        conflict=True,
        risk_multiplier=0.0,
        reason_code=reason_code,
        model=model,
        error=error,
    ).as_dict()


def _actionable(analysis: dict[str, Any]) -> bool:
    return analysis.get("state") == "CONFIRMED" and analysis.get("action") in {"BUY", "SELL"}


def _compact_context(snapshot: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    instrument = snapshot.get("instrument") or {}
    quote = snapshot.get("quote") or {}
    point = float(instrument.get("point") or 0.01)
    bid = float(quote.get("bid") or 0.0)
    ask = float(quote.get("ask") or 0.0)
    spread_points = (ask - bid) / point if point > 0 and ask >= bid else None
    return {
        "symbol": str(instrument.get("symbol") or analysis.get("symbol") or "").upper(),
        "decision_time": analysis.get("decision_time"),
        "candidate": {
            "action": analysis.get("action"),
            "state": analysis.get("state"),
            "reason": analysis.get("reason"),
            "entry": analysis.get("entry"),
            "stop": analysis.get("stop"),
            "tp1": analysis.get("tp1"),
            "tp2": analysis.get("tp2"),
            "risk_fraction": analysis.get("risk_fraction"),
            "confidence_score": analysis.get("confidence_score"),
        },
        "market": {
            "h1_bias": analysis.get("h1_bias"),
            "h4_bias": analysis.get("h4_bias"),
            "support_zones": analysis.get("support_zones") or [],
            "resistance_zones": analysis.get("resistance_zones") or [],
            "ict": analysis.get("ict"),
            "spread_points": round(spread_points, 2) if spread_points is not None else None,
        },
    }


def _response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    for item in payload.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                return part["text"]
    raise ValueError("OPENAI_RESPONSE_MISSING_OUTPUT_TEXT")


def _validate_result(data: dict[str, Any], model: str) -> dict[str, Any]:
    decision = str(data.get("decision") or "").upper()
    if decision not in {"ALLOW", "REDUCE_RISK", "BLOCK"}:
        raise ValueError("AI_GATE_INVALID_DECISION")

    score = float(data.get("context_score"))
    if not 0.0 <= score <= 1.0:
        raise ValueError("AI_GATE_INVALID_CONTEXT_SCORE")

    multiplier = float(data.get("risk_multiplier"))
    if multiplier not in {0.0, 0.25, 0.5, 0.75, 1.0}:
        raise ValueError("AI_GATE_INVALID_RISK_MULTIPLIER")
    if decision == "BLOCK":
        multiplier = 0.0
    elif decision == "ALLOW":
        multiplier = 1.0
    elif multiplier <= 0.0 or multiplier >= 1.0:
        raise ValueError("AI_GATE_REDUCE_REQUIRES_PARTIAL_MULTIPLIER")

    regime = str(data.get("regime") or "UNKNOWN").upper()
    if regime not in {"TREND", "RANGE", "TRANSITION", "UNKNOWN"}:
        regime = "UNKNOWN"

    reason_code = str(data.get("reason_code") or "UNSPECIFIED")[:80]
    return AIGateResult(
        schema=AI_GATE_SCHEMA,
        status="OK",
        decision=decision,
        context_score=round(score, 4),
        regime=regime,
        conflict=bool(data.get("conflict")),
        risk_multiplier=multiplier,
        reason_code=reason_code,
        model=model,
        error=None,
    ).as_dict()


def evaluate_context(
    snapshot: dict[str, Any],
    analysis: dict[str, Any],
    *,
    api_key: str | None = None,
    enabled: bool | None = None,
    model: str | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Evaluate one deterministic candidate. Fail closed under every exception."""
    if not _actionable(analysis):
        return _blocked("NOT_CALLED", "NO_CONFIRMED_CANDIDATE")

    if enabled is None:
        enabled = os.environ.get("MIDAS_AI_GATE_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
    model = model or os.environ.get("MIDAS_OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    api_key = (api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("MIDAS_OPENAI_API_KEY") or "").strip()
    timeout_seconds = timeout_seconds or float(os.environ.get("MIDAS_AI_TIMEOUT_SECONDS", "8"))

    if not enabled:
        return _blocked("DISABLED", "AI_GATE_DISABLED", model=model)
    if not api_key:
        return _blocked("MISCONFIGURED", "OPENAI_API_KEY_MISSING", model=model)

    schema = {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["ALLOW", "REDUCE_RISK", "BLOCK"]},
            "context_score": {"type": "number", "minimum": 0, "maximum": 1},
            "regime": {"type": "string", "enum": ["TREND", "RANGE", "TRANSITION", "UNKNOWN"]},
            "conflict": {"type": "boolean"},
            "risk_multiplier": {"type": "number", "enum": [0, 0.25, 0.5, 0.75, 1]},
            "reason_code": {"type": "string", "minLength": 1, "maxLength": 80},
        },
        "required": ["decision", "context_score", "regime", "conflict", "risk_multiplier", "reason_code"],
        "additionalProperties": False,
    }
    system = (
        "You are MIDAS Context Gate. You do not generate trades. "
        "Evaluate only the deterministic candidate provided. "
        "Never change direction, entry, stop, targets, or lot size. "
        "Use ALLOW only when context supports the candidate without material conflict. "
        "Use REDUCE_RISK when the setup remains valid but context is mixed. "
        "Use BLOCK when context materially conflicts, is unclear, or risk is elevated. "
        "Do not treat confidence as a probability of profit."
    )
    body = {
        "model": model,
        "store": False,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(_compact_context(snapshot, analysis), separators=(",", ":"), allow_nan=False)}]},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "midas_context_gate",
                "strict": True,
                "schema": schema,
            }
        },
        "max_output_tokens": 300,
    }

    request = Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(body, separators=(",", ":"), allow_nan=False).encode("utf-8"),
        method="POST",
        headers={
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
            "user-agent": "midas-ai-gate/1",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        parsed = json.loads(_response_text(payload))
        return _validate_result(parsed, model)
    except HTTPError as exc:
        return _blocked("ERROR", f"OPENAI_HTTP_{exc.code}", model=model, error=f"HTTP_{exc.code}")
    except URLError:
        return _blocked("ERROR", "OPENAI_NETWORK_ERROR", model=model, error="NETWORK_ERROR")
    except Exception as exc:
        return _blocked("ERROR", "AI_GATE_ERROR", model=model, error=type(exc).__name__)
