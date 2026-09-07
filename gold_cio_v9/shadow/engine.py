"""Deterministic BUY/SELL/ABSTAIN shadow decision gate; never routes orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256


@dataclass(frozen=True)
class ShadowFeed:
    acquired_at: datetime
    latest_bar_time: datetime
    latest_price: float
    data_snapshot_hash: str


@dataclass(frozen=True)
class ShadowCandidate:
    candidate_id: str
    contract: str
    direction: str
    event_time: datetime


@dataclass(frozen=True)
class ShadowDecision:
    action: str
    reason: str
    signal_id: str | None
    contract: str | None
    entry_price: float | None
    execution_allowed: bool = False


def _signal_id(candidate: ShadowCandidate, strategy_version: str) -> str:
    raw = "|".join((strategy_version, candidate.candidate_id, candidate.contract,
                    candidate.direction, candidate.event_time.isoformat())).encode()
    return sha256(raw).hexdigest()


def decide_shadow(
    *, candidate: ShadowCandidate | None, feed: ShadowFeed,
    strategy_version: str, seen_signal_ids: set[str],
    max_feed_age: timedelta = timedelta(minutes=20),
    max_candidate_age: timedelta = timedelta(minutes=15),
    real_orders_enabled: bool = False,
) -> ShadowDecision:
    if real_orders_enabled:
        raise RuntimeError("LIVE_ORDERS_FORBIDDEN_IN_SHADOW")
    if feed.acquired_at.tzinfo is None or feed.latest_bar_time.tzinfo is None:
        raise ValueError("timezone-aware feed timestamps required")
    if feed.latest_price <= 0 or not feed.data_snapshot_hash.strip():
        return ShadowDecision("ABSTAIN", "INVALID_FEED", None, None, None)
    feed_age = feed.acquired_at - feed.latest_bar_time
    if feed_age < timedelta(0):
        return ShadowDecision("ABSTAIN", "FUTURE_DATA_VETO", None, None, None)
    if feed_age > max_feed_age:
        return ShadowDecision("ABSTAIN", "STALE_DATA_VETO", None, None, None)
    if candidate is None:
        return ShadowDecision("ABSTAIN", "NO_NEW_CANDIDATE", None, None, None)
    if candidate.direction not in {"LONG", "SHORT"}:
        return ShadowDecision("ABSTAIN", "INVALID_DIRECTION", None, candidate.contract, None)
    age = feed.acquired_at - candidate.event_time
    if age < timedelta(0):
        return ShadowDecision("ABSTAIN", "FUTURE_CANDIDATE_VETO", None, candidate.contract, None)
    signal_id = _signal_id(candidate, strategy_version)
    if signal_id in seen_signal_ids:
        return ShadowDecision("ABSTAIN", "DUPLICATE_SIGNAL", signal_id, candidate.contract, None)
    if age > max_candidate_age:
        return ShadowDecision("ABSTAIN", "STALE_CANDIDATE_VETO", signal_id, candidate.contract, None)
    action = "BUY" if candidate.direction == "LONG" else "SELL"
    return ShadowDecision(action, "SHADOW_SIGNAL_ONLY", signal_id, candidate.contract, feed.latest_price)
