from datetime import datetime, timedelta, timezone

from gold_cio_v9.data.mt5_snapshot import SCHEMA, seal
from gold_cio_v9.live.mt5_analysis import Candle, analyze_snapshot, resample_closed


def test_resample_uses_only_complete_utc_buckets():
    start = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
    bars = [Candle(start + timedelta(minutes=i), 10 + i, 11 + i, 9 + i, 10.5 + i) for i in range(16)]
    result = resample_closed(bars, 15)
    assert len(result) == 1
    assert result[0].time == start
    assert result[0].open == 10
    assert result[0].close == 24.5


def _snapshot(count: int = 2880):
    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    start = now - timedelta(minutes=count)
    rows = []
    for i in range(count):
        base = 4300 + i * 0.002
        rows.append({
            "event_time": (start + timedelta(minutes=i)).isoformat(),
            "open": base, "high": base + 0.5, "low": base - 0.5, "close": base + 0.1,
            "tick_volume": 10, "spread_points": 20, "real_volume": 0,
        })
    return seal({
        "schema": SCHEMA, "source": "MT5_BROKER_TERMINAL",
        "purpose": "OUTCOME_FREE_BROKER_FEED_PREFLIGHT", "acquired_at": now.isoformat(),
        "instrument": {"symbol": "XAUUSD", "point": 0.01, "trade_contract_size": 100,
                       "volume_min": 0.01, "volume_max": 100, "volume_step": 0.01},
        "quote": {"event_time": now.isoformat(), "bid": 4305.70, "ask": 4305.90},
        "timeframe": "M1_CLOSED_ONLY", "m1_bars": rows,
        "identity_redaction": "NO_ACCOUNT_LOGIN_NO_ACCOUNT_NAME_NO_SERVER",
        "instrument_separation": "BROKER_XAUUSD_NOT_COMEX_GC", "real_orders_allowed": False,
    })


def test_analysis_is_shadow_only_and_never_invents_probability():
    result = analyze_snapshot(_snapshot(), shadow_equity=10_000)
    assert result["execution_allowed"] is False
    assert result["real_orders_allowed"] is False
    assert result["calibrated_probability"] is None
    assert result["calibration_status"] == "UNCALIBRATED"
    assert result["calibration_sample_size"] == 0
    assert result["action"] == "ABSTAIN"


def test_analysis_fails_closed_when_history_is_short():
    result = analyze_snapshot(_snapshot(120))
    assert result["state"] == "WAIT"
    assert result["reason"] == "INSUFFICIENT_CLOSED_BARS"
    assert result["volume_lots"] is None
