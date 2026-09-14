"""Validated broker-feed snapshots for XAUUSD research.

The snapshot is deliberately separate from COMEX GC evidence.  It contains no
order-routing capability and rejects stale, future, malformed, or crossed data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any


SCHEMA = "gold-cio-mt5-xauusd-snapshot-v1"
MAX_QUOTE_AGE = timedelta(seconds=10)
MAX_BAR_AGE = timedelta(minutes=20)
MAX_SPREAD_PRICE = 2.0
MINUTE = timedelta(minutes=1)


def utc(value: str | datetime) -> datetime:
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return value.astimezone(timezone.utc)


def canonical_hash(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body.pop("snapshot_hash", None)
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha256(encoded).hexdigest()


def seal(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["snapshot_hash"] = canonical_hash(result)
    return result


def load_snapshot(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("SNAPSHOT_NOT_OBJECT")
    return payload


@dataclass(frozen=True)
class BrokerFeedReadiness:
    broker_feed_ready: bool
    reason: str
    symbol: str | None
    quote_age_seconds: float | None
    bar_age_minutes: float | None
    spread_price: float | None
    spread_points: float | None
    latest_bid: float | None
    latest_ask: float | None
    latest_closed_bar_time: str | None
    snapshot_hash: str | None
    real_orders_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _finite_positive(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("NONPOSITIVE_OR_NONFINITE_VALUE")
    return number


def _validate_bars(bars: Any, acquired_at: datetime) -> datetime:
    if not isinstance(bars, list) or not bars:
        raise ValueError("MISSING_M1_BARS")
    previous = None
    for row in bars:
        if not isinstance(row, dict):
            raise ValueError("INVALID_BAR_OBJECT")
        start = utc(row["event_time"])
        if start.second or start.microsecond:
            raise ValueError("UNALIGNED_BAR")
        if start + MINUTE > acquired_at:
            raise ValueError("INCOMPLETE_OR_FUTURE_BAR")
        if previous is not None and start <= previous:
            raise ValueError("DUPLICATE_OR_UNSORTED_BAR")
        previous = start
        open_, high, low, close = (_finite_positive(row[k]) for k in ("open", "high", "low", "close"))
        if not low <= min(open_, close) <= max(open_, close) <= high:
            raise ValueError("INVALID_OHLC")
        for key in ("tick_volume", "real_volume", "spread_points"):
            number = float(row.get(key, 0))
            if not math.isfinite(number) or number < 0:
                raise ValueError("INVALID_BAR_ACTIVITY")
    assert previous is not None
    return previous + MINUTE


def validate_snapshot(
    payload: dict[str, Any], *, observed_at: datetime,
    expected_symbol: str | None = None,
    max_quote_age: timedelta = MAX_QUOTE_AGE,
    max_bar_age: timedelta = MAX_BAR_AGE,
    max_spread_price: float = MAX_SPREAD_PRICE,
) -> BrokerFeedReadiness:
    """Return a fail-closed, outcome-free broker-feed readiness decision."""
    observed_at = utc(observed_at)
    symbol = None
    try:
        if payload.get("schema") != SCHEMA:
            raise ValueError("SCHEMA_MISMATCH")
        if payload.get("source") != "MT5_BROKER_TERMINAL":
            raise ValueError("SOURCE_MISMATCH")
        if payload.get("real_orders_allowed") is not False:
            raise ValueError("ORDER_PERMISSION_VETO")
        if payload.get("snapshot_hash") != canonical_hash(payload):
            raise ValueError("SNAPSHOT_HASH_MISMATCH")
        instrument = payload.get("instrument")
        quote = payload.get("quote")
        if not isinstance(instrument, dict) or not isinstance(quote, dict):
            raise ValueError("MISSING_INSTRUMENT_OR_QUOTE")
        symbol = str(instrument.get("symbol", "")).strip()
        if not symbol:
            raise ValueError("MISSING_SYMBOL")
        if expected_symbol and symbol.casefold() != expected_symbol.strip().casefold():
            raise ValueError("SYMBOL_MISMATCH")
        point = _finite_positive(instrument.get("point"))
        acquired_at = utc(payload["acquired_at"])
        quote_time = utc(quote["event_time"])
        if acquired_at > observed_at + timedelta(seconds=2):
            raise ValueError("FUTURE_ACQUISITION")
        if quote_time > observed_at:
            raise ValueError("FUTURE_QUOTE")
        bid, ask = _finite_positive(quote["bid"]), _finite_positive(quote["ask"])
        if ask < bid:
            raise ValueError("CROSSED_QUOTE")
        spread = ask - bid
        if spread > max_spread_price:
            raise ValueError("ABNORMAL_SPREAD")
        latest_close = _validate_bars(payload.get("m1_bars"), acquired_at)
        quote_age = observed_at - quote_time
        bar_age = observed_at - latest_close
        if quote_age < timedelta(0) or bar_age < timedelta(0):
            raise ValueError("FUTURE_DATA")
        if quote_age > max_quote_age:
            raise ValueError("STALE_QUOTE_VETO")
        if bar_age > max_bar_age:
            raise ValueError("STALE_BAR_VETO")
        return BrokerFeedReadiness(
            True, "BROKER_FEED_READY", symbol, quote_age.total_seconds(),
            bar_age.total_seconds() / 60, spread, spread / point, bid, ask,
            latest_close.isoformat(), payload["snapshot_hash"],
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        reason = str(exc) if str(exc) else exc.__class__.__name__
        return BrokerFeedReadiness(False, reason, symbol, None, None, None, None,
                                   None, None, None, payload.get("snapshot_hash"))

