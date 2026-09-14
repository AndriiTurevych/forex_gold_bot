"""MIDAS v10 Lean: deterministic, fail-closed XAUUSD decision layer.

The module composes the preregistered EXP-0001 event sequence with higher-timeframe
agreement, session, exposure and independent risk gates. It never sends orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Literal

from gold_cio_v9.experiments.exp0001_signal import (
    FVGZone,
    TimedStructure,
    TimedSweep,
    generate_exp0001_signal,
)
from gold_cio_v9.ict_engine.features import Bar
from gold_cio_v9.risk.gate import RiskState, evaluate as evaluate_risk
from gold_cio_v9.risk.position_sizing import SizingInputs, size_position

Bias = Literal["LONG", "SHORT", "NEUTRAL"]


@dataclass(frozen=True)
class MidasConfig:
    session_start_utc: int = 6
    session_end_utc: int = 20
    max_trades_per_day: int = 2
    risk_fraction: float = 0.0025
    daily_loss_lock: float = 0.005
    stop_buffer_atr: float = 0.10
    tp1_r: float = 1.0
    tp2_r: float = 2.0


@dataclass(frozen=True)
class MidasInputs:
    decision_time: datetime
    h1_bias: Bias
    h4_bias: Bias
    trades_today: int
    equity: float
    point_value: float
    atr: float
    risk_state: RiskState
    htf_location_ok: bool
    sweep: TimedSweep
    structure: TimedStructure
    zone: FVGZone
    retest_bar: Bar


@dataclass(frozen=True)
class MidasDecision:
    action: Literal["BUY", "SELL", "ABSTAIN"]
    reason: str
    entry: float | None = None
    stop: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    units: float = 0.0
    cash_risk: float = 0.0
    execution_allowed: bool = False


def _abstain(reason: str) -> MidasDecision:
    return MidasDecision("ABSTAIN", reason)


def _utc_hour(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("decision_time must be timezone-aware")
    return value.astimezone(timezone.utc).hour


def evaluate_midas(inputs: MidasInputs, config: MidasConfig = MidasConfig()) -> MidasDecision:
    """Return a fully sized shadow decision or fail closed with an explicit reason."""
    if not (0 <= config.session_start_utc < config.session_end_utc <= 24):
        return _abstain("INVALID_SESSION_CONFIG")
    if config.max_trades_per_day <= 0:
        return _abstain("INVALID_TRADE_LIMIT")
    numeric = (inputs.equity, inputs.point_value, inputs.atr)
    if not all(isfinite(v) for v in numeric) or min(numeric) <= 0:
        return _abstain("INVALID_SIZING_INPUT")
    if inputs.trades_today < 0:
        return _abstain("INVALID_TRADE_COUNT")
    try:
        hour = _utc_hour(inputs.decision_time)
    except (ValueError, OverflowError):
        return _abstain("INVALID_DECISION_TIME")
    if not config.session_start_utc <= hour < config.session_end_utc:
        return _abstain("OUTSIDE_LONDON_NEW_YORK_SESSION")
    if inputs.trades_today >= config.max_trades_per_day:
        return _abstain("DAILY_TRADE_LIMIT")
    if inputs.risk_state.daily_loss_fraction >= config.daily_loss_lock:
        return _abstain("MIDAS_DAILY_LOSS_LOCK")
    if inputs.risk_state.risk_fraction != config.risk_fraction:
        return _abstain("RISK_NOT_LOCKED_AT_0_25_PERCENT")

    if not isinstance(inputs.h1_bias, str) or not isinstance(inputs.h4_bias, str):
        return _abstain("INVALID_REGIME")
    h1 = inputs.h1_bias.upper()
    h4 = inputs.h4_bias.upper()
    if h1 not in {"LONG", "SHORT", "NEUTRAL"} or h4 not in {"LONG", "SHORT", "NEUTRAL"}:
        return _abstain("INVALID_REGIME")
    if h1 != h4 or h1 == "NEUTRAL":
        return _abstain("HTF_REGIME_DISAGREEMENT")

    if (
        not isfinite(inputs.sweep.sweep.level)
        or not isfinite(inputs.sweep.sweep.depth)
        or inputs.sweep.sweep.depth <= 0
    ):
        return _abstain("INVALID_SWEEP")
    try:
        signal = generate_exp0001_signal(
            htf_location_ok=inputs.htf_location_ok,
            sweep=inputs.sweep,
            structure=inputs.structure,
            zone=inputs.zone,
            retest_time=inputs.decision_time,
            retest_bar=inputs.retest_bar,
        )
    except (TypeError, ValueError):
        return _abstain("INVALID_ICT_INPUT")
    if signal is None:
        return _abstain("INCOMPLETE_ICT_SEQUENCE")
    if signal.direction != h1:
        return _abstain("SIGNAL_REGIME_CONFLICT")

    risk = evaluate_risk(inputs.risk_state)
    if not risk.approved:
        return _abstain(risk.reason)

    entry = signal.entry_price
    buffer = inputs.atr * config.stop_buffer_atr
    if signal.direction == "LONG":
        sweep_extreme = inputs.sweep.sweep.level - inputs.sweep.sweep.depth
        stop = sweep_extreme - buffer
        if stop >= entry:
            return _abstain("INVALID_LONG_STOP")
        one_r = entry - stop
        action = "BUY"
        tp1 = entry + config.tp1_r * one_r
        tp2 = entry + config.tp2_r * one_r
    else:
        sweep_extreme = inputs.sweep.sweep.level + inputs.sweep.sweep.depth
        stop = sweep_extreme + buffer
        if stop <= entry:
            return _abstain("INVALID_SHORT_STOP")
        one_r = stop - entry
        action = "SELL"
        tp1 = entry - config.tp1_r * one_r
        tp2 = entry - config.tp2_r * one_r

    try:
        sizing = size_position(SizingInputs(
            equity=inputs.equity,
            risk_fraction=config.risk_fraction,
            entry=entry,
            stop=stop,
            point_value=inputs.point_value,
            max_risk_fraction=config.risk_fraction,
        ))
    except ValueError:
        return _abstain("POSITION_SIZING_REJECTED")

    return MidasDecision(
        action=action,
        reason="SHADOW_APPROVED",
        entry=entry,
        stop=stop,
        tp1=tp1,
        tp2=tp2,
        units=sizing.units,
        cash_risk=sizing.cash_risk,
        execution_allowed=False,
    )
