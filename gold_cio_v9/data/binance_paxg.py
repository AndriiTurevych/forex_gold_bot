"""Fail-closed Binance PAXG/USDT adapter for MIDAS gold-proxy research.

PAXG is a separate crypto venue and must never be relabelled as COMEX GC or
broker XAUUSD.  This module only establishes outcome-free data readiness.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Iterable, Mapping


SYMBOL = "PAXGUSDT"
SOURCE_ID = "binance:spot:public"
ROLE = "GOLD_PROXY_ONLY"


@dataclass(frozen=True)
class PaxgQuote:
    acquired_at: datetime
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float:
        return (self.ask - self.bid) / self.mid * 10_000.0


@dataclass(frozen=True)
class PaxgBar:
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: int


def _aware_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _positive(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return parsed


def _millis(value: Any, name: str) -> datetime:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return datetime.fromtimestamp(parsed / 1000.0, tz=timezone.utc)


def parse_book_ticker(payload: Mapping[str, Any], *, acquired_at: datetime) -> PaxgQuote:
    if str(payload.get("symbol", "")).upper() != SYMBOL:
        raise ValueError("PAXG_PROXY_SYMBOL_MISMATCH")
    acquired = _aware_utc(acquired_at, "acquired_at")
    bid = _positive(payload.get("bidPrice"), "bidPrice")
    ask = _positive(payload.get("askPrice"), "askPrice")
    if ask <= bid:
        raise ValueError("PAXG_PROXY_CROSSED_OR_ZERO_SPREAD")
    return PaxgQuote(acquired_at=acquired, bid=bid, ask=ask)


def parse_klines(rows: Iterable[list[Any]]) -> tuple[PaxgBar, ...]:
    bars: list[PaxgBar] = []
    seen: set[datetime] = set()
    for row in rows:
        if not isinstance(row, list) or len(row) < 9:
            raise ValueError("PAXG_PROXY_MALFORMED_KLINE")
        opened = _millis(row[0], "open_time")
        closed = _millis(row[6], "close_time")
        if closed <= opened:
            raise ValueError("PAXG_PROXY_INVALID_INTERVAL")
        if opened in seen:
            raise ValueError("PAXG_PROXY_DUPLICATE_KLINE")
        seen.add(opened)
        o = _positive(row[1], "open")
        h = _positive(row[2], "high")
        l = _positive(row[3], "low")
        c = _positive(row[4], "close")
        volume = float(row[5])
        trades = int(row[8])
        if not isfinite(volume) or volume < 0 or trades < 0:
            raise ValueError("PAXG_PROXY_INVALID_ACTIVITY")
        if h < max(o, c) or l > min(o, c) or h < l:
            raise ValueError("PAXG_PROXY_INVALID_OHLC")
        bars.append(PaxgBar(opened, closed, o, h, l, c, volume, trades))
    if not bars:
        raise ValueError("PAXG_PROXY_EMPTY_KLINES")
    bars.sort(key=lambda bar: bar.open_time)
    return tuple(bars)


def evaluate_proxy_readiness(
    *, quote_payload: Mapping[str, Any], kline_rows: Iterable[list[Any]],
    acquired_at: datetime, max_bar_age: timedelta = timedelta(minutes=2),
    max_spread_bps: float = 2.0,
) -> dict[str, Any]:
    if max_bar_age <= timedelta(0) or max_spread_bps <= 0:
        raise ValueError("invalid readiness thresholds")
    quote = parse_book_ticker(quote_payload, acquired_at=acquired_at)
    bars = parse_klines(kline_rows)
    closed = tuple(bar for bar in bars if bar.close_time <= quote.acquired_at)
    reasons: list[str] = []
    latest = closed[-1] if closed else None
    if latest is None:
        reasons.append("NO_CLOSED_BAR")
        age_seconds = None
    else:
        age = quote.acquired_at - latest.close_time
        age_seconds = age.total_seconds()
        if age < timedelta(0):
            reasons.append("FUTURE_BAR_VETO")
        elif age > max_bar_age:
            reasons.append("STALE_BAR_VETO")
    if quote.spread_bps > max_spread_bps:
        reasons.append("WIDE_SPREAD_VETO")

    normalized = {
        "symbol": SYMBOL,
        "role": ROLE,
        "acquired_at": quote.acquired_at.isoformat(),
        "bid": quote.bid,
        "ask": quote.ask,
        "latest_closed_bar": latest.close_time.isoformat() if latest else None,
        "latest_close": latest.close if latest else None,
    }
    snapshot_hash = sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    ready = not reasons
    return {
        "schema": "gold-cio-paxg-proxy-preflight-v1",
        "experiment_id": "EXP-0006",
        "symbol": SYMBOL,
        "source_id": SOURCE_ID,
        "instrument_role": ROLE,
        "status": "DATA_READY" if ready else "VETO",
        "data_ready": ready,
        "reasons": reasons,
        "acquired_at": quote.acquired_at.isoformat(),
        "latest_closed_bar_time": latest.close_time.isoformat() if latest else None,
        "bar_age_seconds": age_seconds,
        "bid": quote.bid,
        "ask": quote.ask,
        "spread_bps": quote.spread_bps,
        "snapshot_hash": snapshot_hash,
        "quote_timestamp_quality": "RECEIPT_TIME_ONLY",
        "strategy_outcomes_generated": False,
        "formal_gc_verdict_allowed": False,
        "real_orders_allowed": False,
    }
