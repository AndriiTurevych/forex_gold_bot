"""Independent deterministic risk gate. AI/ML cannot override these controls."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class RiskState:
    risk_fraction: float
    daily_loss_fraction: float
    weekly_drawdown_fraction: float
    spread_ok: bool
    data_fresh: bool
    feed_agreement: bool
    high_impact_event_lock: bool


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str


def _valid_fraction(value: float) -> bool:
    return isfinite(value) and value >= 0.0


def evaluate(state: RiskState) -> RiskDecision:
    """Fail closed on malformed state before evaluating trading limits."""
    if not _valid_fraction(state.risk_fraction):
        return RiskDecision(False, "INVALID_RISK_FRACTION")
    if not _valid_fraction(state.daily_loss_fraction):
        return RiskDecision(False, "INVALID_DAILY_LOSS")
    if not _valid_fraction(state.weekly_drawdown_fraction):
        return RiskDecision(False, "INVALID_WEEKLY_DRAWDOWN")
    if not all(isinstance(v, bool) for v in (
        state.spread_ok,
        state.data_fresh,
        state.feed_agreement,
        state.high_impact_event_lock,
    )):
        return RiskDecision(False, "INVALID_BOOLEAN_STATE")
    if state.risk_fraction > 0.0025:
        return RiskDecision(False, "RISK_PER_TRADE_LIMIT")
    if state.daily_loss_fraction >= 0.01:
        return RiskDecision(False, "DAILY_LOSS_LOCK")
    if state.weekly_drawdown_fraction >= 0.025:
        return RiskDecision(False, "WEEKLY_DRAWDOWN_LOCK")
    if not state.data_fresh:
        return RiskDecision(False, "STALE_DATA")
    if not state.feed_agreement:
        return RiskDecision(False, "FEED_DISAGREEMENT")
    if not state.spread_ok:
        return RiskDecision(False, "SPREAD_VETO")
    if state.high_impact_event_lock:
        return RiskDecision(False, "EVENT_LOCK")
    return RiskDecision(True, "APPROVED")
