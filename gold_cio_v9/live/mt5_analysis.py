"""Deterministic MIDAS v2 market analysis for validated MT5 XAUUSD snapshots.

Primary strategy: CRT + TBS failed-breakout setup on closed candles.
Supported models: H4->M15 and H1->M5. ICT primitives remain available only for
research/context; they no longer create the default trade candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import floor, isfinite
from typing import Any, Iterable

from gold_cio_v9.ict_engine.features import Bar
from gold_cio_v9.live.crt_tbs import detect_crt_tbs
from gold_cio_v9.strategies.confidence import ConfidenceFactors, score_confidence


ANALYSIS_SCHEMA = "midas-mt5-shadow-analysis-v2"
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
    """Resample M1 into UTC-aligned complete buckets only."""
    if minutes < 1:
        raise ValueError("minutes must be positive")
    grouped: dict[datetime, list[Candle]] = {}
    for bar in bars:
        total = bar.time.hour * 60 + bar.time.minute
        minute = floor(total / minutes) * minutes
        bucket = bar.time.replace(hour=minute // 60, minute=minute % 60, second=0, microsecond=0)
        grouped.setdefault(bucket, []).append(bar)
    out: list[Candle] = []
    for bucket, rows in sorted(grouped.items()):
        if len(rows) != minutes:
            continue
        expected = [bucket + timedelta(minutes=i) for i in range(minutes)]
        if [r.time for r in rows] != expected:
            continue
        out.append(Candle(
            bucket,
            rows[0].open,
            max(r.high for r in rows),
            min(r.low for r in rows),
            rows[-1].close,
        ))
    return out


def _atr(bars: list[Candle], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(len(bars) - period, len(bars)):
        current = bars[i]
        previous = bars[i - 1]
        trs.append(max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        ))
    value = sum(trs) / period
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
        candidates = sorted(
            (x for x in levels if (x <= price if side == "support" else x >= price)),
            reverse=side == "support",
        )
        result: list[dict[str, float]] = []
        for level in candidates:
            if any(abs(level - z["mid"]) <= half_width for z in result):
                continue
            result.append({
                "low": round(level - half_width, 2),
                "high": round(level + half_width, 2),
                "mid": round(level, 2),
            })
            if len(result) == 3:
                break
        return result

    return cluster(lows, "support"), cluster(highs, "resistance")


def _round_volume(raw: float, instrument: dict[str, Any]) -> float:
    minimum = float(instrument.get("volume_min") or 0.01)
    maximum = float(instrument.get("volume_max") or raw)
    step = float(instrument.get("volume_step") or minimum)
    if raw <= 0 or step <= 0:
        return 0.0
    value = min(maximum, floor(raw / step + 1e-12) * step)
    return round(value, 8) if value >= minimum else 0.0


def _size_lots(cash_risk: float, distance: float, instrument: dict[str, Any]) -> float:
    """Size by broker tick economics when available; fall back to contract size."""
    if cash_risk <= 0 or distance <= 0:
        return 0.0
    tick_size = float(instrument.get("trade_tick_size") or 0.0)
    tick_value_loss = float(
        instrument.get("trade_tick_value_loss")
        or instrument.get("trade_tick_value")
        or 0.0
    )
    if tick_size > 0 and tick_value_loss > 0:
        risk_per_lot = (distance / tick_size) * tick_value_loss
    else:
        contract_size = float(instrument.get("trade_contract_size") or 100.0)
        risk_per_lot = distance * contract_size
    if risk_per_lot <= 0:
        return 0.0
    return _round_volume(cash_risk / risk_per_lot, instrument)


def analyze_snapshot(snapshot: dict[str, Any], *, shadow_equity: float | None = None) -> dict[str, Any]:
    bars = _m1(snapshot)
    m5 = resample_closed(bars, 5)
    m15 = resample_closed(bars, 15)
    h1 = resample_closed(bars, 60)
    h4 = resample_closed(bars, 240)
    quote = snapshot["quote"]
    bid, ask = float(quote["bid"]), float(quote["ask"])
    price = (bid + ask) / 2
    atr15 = _atr(m15)

    result: dict[str, Any] = {
        "schema": ANALYSIS_SCHEMA,
        "strategy": "CRT_TBS",
        "snapshot_hash": snapshot["snapshot_hash"],
        "symbol": str(snapshot["instrument"]["symbol"]).upper(),
        "decision_time": quote["event_time"],
        "signal_id": None,
        "setup_model": None,
        "action": "ABSTAIN",
        "state": "WAIT",
        "reason": "INSUFFICIENT_CLOSED_BARS",
        "h1_bias": _bias(h1),
        "h4_bias": _bias(h4),
        "entry": None,
        "stop": None,
        "tp1": None,
        "tp2": None,
        "risk_fraction": RISK_FRACTION,
        "cash_risk": None,
        "volume_lots": None,
        "sizing_status": "EQUITY_REQUIRED" if shadow_equity is None else "NOT_APPLICABLE",
        "confidence_score": 0,
        "calibrated_probability": None,
        "calibration_status": "UNCALIBRATED",
        "calibration_sample_size": 0,
        "support_zones": [],
        "resistance_zones": [],
        "timeframes": {
            "m1": len(bars), "m5": len(m5), "m15": len(m15),
            "h1": len(h1), "h4": len(h4),
        },
        "execution_allowed": False,
        "real_orders_allowed": False,
        "warnings": [
            "SHADOW_DEMO_ONLY",
            "AUTOMATED_MACRO_EVENT_CALENDAR_NOT_CONNECTED",
            "PROBABILITY_REQUIRES_EMPIRICAL_CALIBRATION",
        ],
    }
    if atr15 is None or len(m5) < 16 or len(m15) < 16 or len(h1) < 2 or len(h4) < 2:
        return result

    supports, resistances = _zones(m15, price, atr15)
    result["support_zones"], result["resistance_zones"] = supports, resistances

    setup = detect_crt_tbs(h4=h4, h1=h1, m15=m15, m5=m5)
    if setup is None:
        result["reason"] = "INCOMPLETE_CRT_TBS_SEQUENCE"
        return result

    direction = setup.direction
    entry = ask if direction == "LONG" else bid
    stop = float(setup.stop)
    tp1 = float(setup.tp1)
    tp2 = float(setup.tp2)
    distance = abs(entry - stop)
    reward2 = abs(tp2 - entry)

    if distance <= 0:
        result["reason"] = "INVALID_STOP_DISTANCE"
        return result
    if direction == "LONG" and not (stop < entry < tp1 < tp2):
        result["reason"] = "INVALID_LONG_GEOMETRY_AT_QUOTE"
        return result
    if direction == "SHORT" and not (tp2 < tp1 < entry < stop):
        result["reason"] = "INVALID_SHORT_GEOMETRY_AT_QUOTE"
        return result
    if reward2 / distance < 1.80:
        result["reason"] = "RR_BELOW_MINIMUM_AT_QUOTE"
        return result

    h1_match = result["h1_bias"] in {direction, "NEUTRAL"}
    h4_match = result["h4_bias"] in {direction, "NEUTRAL"}
    trend_factor = 1.0 if h1_match and h4_match else 0.65 if h1_match or h4_match else 0.40
    depth_quality = min(1.0, max(0.0, setup.sweep_depth_fraction / 0.15))
    body_quality = min(1.0, setup.body_fraction / 0.65)
    rr_quality = min(1.0, (reward2 / distance) / 3.0)

    factors = ConfidenceFactors(
        trend=trend_factor,
        location=0.95,
        structure=1.0,
        entry_quality=body_quality,
        reward_risk=rr_quality,
        macro=0.50,
        data_quality=0.90,
        model_agreement=0.85 if setup.model == "H4_M15" else 0.75,
    )
    confidence = score_confidence(
        factors,
        mss_confirmed=True,
        retest_confirmed=True,
        event_lock=False,
    )

    result.update({
        "signal_id": setup.signal_id,
        "setup_model": setup.model,
        "action": "BUY" if direction == "LONG" else "SELL",
        "state": "CONFIRMED",
        "reason": "CRT_TBS_FAILED_BREAKOUT_CONFIRMED",
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "confidence_score": confidence.confidence_score,
        "crt_tbs": setup.as_dict(),
        "context_alignment": {
            "h1_match_or_neutral": h1_match,
            "h4_match_or_neutral": h4_match,
        },
    })

    if shadow_equity is not None and isfinite(shadow_equity) and shadow_equity > 0:
        cash_risk = shadow_equity * RISK_FRACTION
        lots = _size_lots(cash_risk, distance, snapshot["instrument"])
        result["cash_risk"] = round(cash_risk, 2)
        result["volume_lots"] = lots if lots > 0 else None
        result["sizing_status"] = "SIZED" if lots > 0 else "BELOW_MINIMUM_VOLUME"

    return result
