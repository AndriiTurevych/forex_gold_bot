"""Deterministic shadow analysis of a validated MT5 XAUUSD snapshot.

This module deliberately does not route orders.  It converts closed M1 bars into
causal higher timeframes, marks nearby support/resistance, and looks for the
locked ICT sequence sweep -> MSS -> FVG -> later retest.  A confidence score is
reported, but it is never mislabeled as probability before calibration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import floor, isfinite
from typing import Any, Iterable

from gold_cio_v9.ict_engine.features import Bar, bearish_fvg, bullish_fvg, detect_liquidity_sweep
from gold_cio_v9.strategies.confidence import ConfidenceFactors, score_confidence


ANALYSIS_SCHEMA = "midas-mt5-shadow-analysis-v1"
RISK_FRACTION = 0.0025


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float

    def feature_bar(self) -> Bar:
        return Bar(self.time.isoformat(), self.open, self.high, self.low, self.close)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


def _m1(snapshot: dict[str, Any]) -> list[Candle]:
    bars = [
        Candle(_utc(row["event_time"]), *(float(row[k]) for k in ("open", "high", "low", "close")))
        for row in snapshot["m1_bars"]
    ]
    if any(a.time >= b.time for a, b in zip(bars, bars[1:])):
        raise ValueError("BARS_NOT_CHRONOLOGICAL")
    return bars


def resample_closed(bars: Iterable[Candle], minutes: int) -> list[Candle]:
    """Resample into UTC buckets, discarding incomplete/gapped buckets."""
    if minutes < 1:
        raise ValueError("minutes must be positive")
    grouped: dict[datetime, list[Candle]] = {}
    for bar in bars:
        minute = floor((bar.time.hour * 60 + bar.time.minute) / minutes) * minutes
        bucket = bar.time.replace(hour=minute // 60, minute=minute % 60, second=0, microsecond=0)
        grouped.setdefault(bucket, []).append(bar)
    out: list[Candle] = []
    for bucket, rows in sorted(grouped.items()):
        if len(rows) != minutes:
            continue
        expected = [bucket + timedelta(minutes=i) for i in range(minutes)]
        if [r.time for r in rows] != expected:
            continue
        out.append(Candle(bucket, rows[0].open, max(r.high for r in rows), min(r.low for r in rows), rows[-1].close))
    return out


def _atr(bars: list[Candle], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    tr = [
        max(b.high - b.low, abs(b.high - bars[i - 1].close), abs(b.low - bars[i - 1].close))
        for i, b in enumerate(bars[-period:], start=len(bars) - period)
    ]
    value = sum(tr) / period
    return value if isfinite(value) and value > 0 else None


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def _bias(bars: list[Candle], period: int = 8) -> str:
    if len(bars) < max(12, period + 3):
        return "NEUTRAL"
    ema = _ema([b.close for b in bars], period)
    close = bars[-1].close
    slope = ema[-1] - ema[-3]
    tolerance = max(close * 0.00005, 1e-9)
    if close > ema[-1] and slope > tolerance:
        return "LONG"
    if close < ema[-1] and slope < -tolerance:
        return "SHORT"
    return "NEUTRAL"


def _pivots(bars: list[Candle], left: int = 2, right: int = 2) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    for i in range(left, len(bars) - right):
        current = bars[i]
        neighbors = bars[i-left:i] + bars[i+1:i+1+right]
        if all(current.high > b.high for b in neighbors):
            highs.append(current.high)
        if all(current.low < b.low for b in neighbors):
            lows.append(current.low)
    return highs, lows


def _zones(bars: list[Candle], price: float, atr: float) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    highs, lows = _pivots(bars[-160:])
    half_width = max(atr * 0.18, price * 0.00005)

    def cluster(levels: list[float], side: str) -> list[dict[str, float]]:
        candidates = sorted((x for x in levels if (x <= price if side == "support" else x >= price)), reverse=side == "support")
        result: list[dict[str, float]] = []
        for level in candidates:
            if any(abs(level - z["mid"]) <= half_width for z in result):
                continue
            result.append({"low": round(level - half_width, 2), "high": round(level + half_width, 2), "mid": round(level, 2)})
            if len(result) == 3:
                break
        return result

    return cluster(lows, "support"), cluster(highs, "resistance")


def _last_swing_levels(bars: list[Candle], end: int) -> tuple[float, float]:
    window = bars[max(0, end - 20):end]
    return max(b.high for b in window), min(b.low for b in window)


def _ict_setup(bars: list[Candle], atr: float) -> dict[str, Any] | None:
    """Return only a recent complete causal sequence; never repair missing legs."""
    start = max(22, len(bars) - 72)
    pending: dict[str, dict[str, Any] | None] = {"LONG": None, "SHORT": None}
    confirmed: list[dict[str, Any]] = []
    for i in range(start, len(bars)):
        current = bars[i]
        ref_high, ref_low = _last_swing_levels(bars, i)
        sweep = detect_liquidity_sweep(current.feature_bar(), ref_high, ref_low)
        if sweep is not None:
            direction = "LONG" if sweep.side == "SSL" else "SHORT"
            pending[direction] = {
                "direction": direction, "sweep_index": i, "sweep_level": sweep.level,
                "sweep_extreme": sweep.level - sweep.depth if direction == "LONG" else sweep.level + sweep.depth,
                "mss_index": None, "zone_index": None, "zone_low": None, "zone_high": None,
            }

        for direction in ("LONG", "SHORT"):
            p = pending[direction]
            if p is None or i <= p["sweep_index"]:
                continue
            prior_high, prior_low = _last_swing_levels(bars, p["sweep_index"])
            body = abs(current.close - current.open)
            mss = (current.close > prior_high if direction == "LONG" else current.close < prior_low) and body >= 0.8 * atr
            if p["mss_index"] is None and mss:
                p["mss_index"] = i
            if p["mss_index"] is None:
                continue
            if p["zone_index"] is None and i >= max(2, p["mss_index"]):
                zone = bullish_fvg(bars[i-2].feature_bar(), current.feature_bar()) if direction == "LONG" else bearish_fvg(bars[i-2].feature_bar(), current.feature_bar())
                if zone is not None:
                    p["zone_low"], p["zone_high"] = zone
                    p["zone_index"] = i
                    continue
            if p["zone_index"] is not None and i > p["zone_index"] and current.high >= p["zone_low"] and current.low <= p["zone_high"]:
                confirmed.append({**p, "retest_index": i, "retest_time": current.time.isoformat()})
                pending[direction] = None
    if not confirmed:
        return None
    latest = confirmed[-1]
    return latest if latest["retest_index"] >= len(bars) - 3 else None


def _round_volume(raw: float, instrument: dict[str, Any]) -> float:
    minimum = float(instrument.get("volume_min") or 0.01)
    maximum = float(instrument.get("volume_max") or raw)
    step = float(instrument.get("volume_step") or minimum)
    value = min(maximum, floor(raw / step + 1e-12) * step)
    return round(value, 8) if value >= minimum else 0.0


def analyze_snapshot(snapshot: dict[str, Any], *, shadow_equity: float | None = None) -> dict[str, Any]:
    bars = _m1(snapshot)
    m15 = resample_closed(bars, 15)
    h1 = resample_closed(bars, 60)
    h4 = resample_closed(bars, 240)
    quote = snapshot["quote"]
    bid, ask = float(quote["bid"]), float(quote["ask"])
    price = (bid + ask) / 2
    atr = _atr(m15)
    result: dict[str, Any] = {
        "schema": ANALYSIS_SCHEMA,
        "snapshot_hash": snapshot["snapshot_hash"],
        "symbol": str(snapshot["instrument"]["symbol"]).upper(),
        "decision_time": quote["event_time"],
        "action": "ABSTAIN", "state": "WAIT", "reason": "INSUFFICIENT_CLOSED_BARS",
        "h1_bias": _bias(h1), "h4_bias": _bias(h4),
        "entry": None, "stop": None, "tp1": None, "tp2": None,
        "risk_fraction": RISK_FRACTION, "cash_risk": None, "volume_lots": None,
        "sizing_status": "EQUITY_REQUIRED" if shadow_equity is None else "NOT_APPLICABLE",
        "confidence_score": 0, "calibrated_probability": None,
        "calibration_status": "UNCALIBRATED", "calibration_sample_size": 0,
        "support_zones": [], "resistance_zones": [],
        "timeframes": {"m1": len(bars), "m15": len(m15), "h1": len(h1), "h4": len(h4)},
        "execution_allowed": False, "real_orders_allowed": False,
        "warnings": ["SHADOW_ONLY", "MACRO_EVENT_CALENDAR_NOT_CONNECTED", "PROBABILITY_REQUIRES_100_RESOLVED_SIGNALS"],
    }
    if atr is None or len(h1) < 24 or len(h4) < 8:
        return result
    supports, resistances = _zones(m15, price, atr)
    result["support_zones"], result["resistance_zones"] = supports, resistances
    if result["h1_bias"] != result["h4_bias"] or result["h1_bias"] == "NEUTRAL":
        result["reason"] = "HTF_REGIME_DISAGREEMENT"
        return result
    setup = _ict_setup(m15, atr)
    if setup is None:
        result["reason"] = "INCOMPLETE_ICT_SEQUENCE"
        return result
    if setup["direction"] != result["h1_bias"]:
        result["reason"] = "SIGNAL_REGIME_CONFLICT"
        return result

    direction = setup["direction"]
    entry = ask if direction == "LONG" else bid
    stop = setup["sweep_extreme"] - 0.1 * atr if direction == "LONG" else setup["sweep_extreme"] + 0.1 * atr
    distance = abs(entry - stop)
    if distance <= 0 or (direction == "LONG" and stop >= entry) or (direction == "SHORT" and stop <= entry):
        result["reason"] = "INVALID_STOP_GEOMETRY"
        return result
    tp1 = entry + distance if direction == "LONG" else entry - distance
    tp2 = entry + 2 * distance if direction == "LONG" else entry - 2 * distance
    factors = ConfidenceFactors(0.9, 0.75, 1.0, 0.9, 1.0, 0.5, 0.8, 0.6)
    confidence = score_confidence(factors, mss_confirmed=True, retest_confirmed=True, event_lock=False)
    result.update({
        "action": "BUY" if direction == "LONG" else "SELL", "state": "CONFIRMED",
        "reason": "SHADOW_ICT_CONFIRMED", "entry": round(entry, 2), "stop": round(stop, 2),
        "tp1": round(tp1, 2), "tp2": round(tp2, 2), "confidence_score": confidence.confidence_score,
        "ict": {k: v for k, v in setup.items() if k not in {"sweep_index", "mss_index", "zone_index", "retest_index"}},
    })
    if shadow_equity is not None and isfinite(shadow_equity) and shadow_equity > 0:
        cash_risk = shadow_equity * RISK_FRACTION
        contract_size = float(snapshot["instrument"].get("trade_contract_size") or 100.0)
        lots = _round_volume(cash_risk / (distance * contract_size), snapshot["instrument"])
        result["cash_risk"] = round(cash_risk, 2)
        result["volume_lots"] = lots if lots > 0 else None
        result["sizing_status"] = "SIZED" if lots > 0 else "BELOW_MINIMUM_VOLUME"
    return result
