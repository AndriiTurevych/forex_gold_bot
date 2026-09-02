"""Broker-neutral real-time market-data health checks."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class FeedLimits:
    max_age_ms: float = 500.0
    max_cross_feed_diff_points: float = 0.50
    max_spread_points: float = 1.00

    def __post_init__(self) -> None:
        if min(self.max_age_ms, self.max_cross_feed_diff_points, self.max_spread_points) <= 0:
            raise ValueError("feed limits must be positive")


@dataclass(frozen=True)
class FeedSnapshot:
    primary_bid: float
    primary_ask: float
    secondary_mid: float
    primary_age_ms: float
    secondary_age_ms: float
    sequence_gap: bool = False
    out_of_order: bool = False


@dataclass(frozen=True)
class FeedDecision:
    healthy: bool
    reason: str
    primary_mid: float
    spread_points: float
    cross_feed_diff_points: float


def evaluate_feed(snapshot: FeedSnapshot, limits: FeedLimits = FeedLimits()) -> FeedDecision:
    values = (
        snapshot.primary_bid,
        snapshot.primary_ask,
        snapshot.secondary_mid,
        snapshot.primary_age_ms,
        snapshot.secondary_age_ms,
    )
    if not all(isfinite(v) for v in values):
        return FeedDecision(False, "INVALID_FEED_METRIC", 0.0, 0.0, 0.0)
    if min(snapshot.primary_bid, snapshot.primary_ask, snapshot.secondary_mid) <= 0:
        return FeedDecision(False, "INVALID_PRICE", 0.0, 0.0, 0.0)
    if snapshot.primary_age_ms < 0 or snapshot.secondary_age_ms < 0:
        return FeedDecision(False, "INVALID_FEED_AGE", 0.0, 0.0, 0.0)
    spread = snapshot.primary_ask - snapshot.primary_bid
    mid = (snapshot.primary_bid + snapshot.primary_ask) / 2.0
    diff = abs(mid - snapshot.secondary_mid)
    if spread < 0:
        return FeedDecision(False, "CROSSED_PRIMARY_QUOTE", mid, spread, diff)
    if snapshot.sequence_gap:
        return FeedDecision(False, "SEQUENCE_GAP", mid, spread, diff)
    if snapshot.out_of_order:
        return FeedDecision(False, "OUT_OF_ORDER_EVENT", mid, spread, diff)
    if snapshot.primary_age_ms > limits.max_age_ms:
        return FeedDecision(False, "PRIMARY_FEED_STALE", mid, spread, diff)
    if snapshot.secondary_age_ms > limits.max_age_ms:
        return FeedDecision(False, "SECONDARY_FEED_STALE", mid, spread, diff)
    if spread > limits.max_spread_points:
        return FeedDecision(False, "SPREAD_VETO", mid, spread, diff)
    if diff > limits.max_cross_feed_diff_points:
        return FeedDecision(False, "CROSS_FEED_DISAGREEMENT", mid, spread, diff)
    return FeedDecision(True, "FEED_HEALTHY", mid, spread, diff)
