from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.experiments.exp0001_evidence_book import EvidenceBook, EvidenceBookCell, EvidenceTrade
from gold_cio_v9.validation.exp0001_regimes import MacroEvent, build_regime_labels


def _bars(days=30):
    t0 = datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc)
    out = []
    for d in range(days):
        base = 100 + d * 0.1
        for minute, close in [(0, base), (1, base + 1), (2, base - 1), (3, base + 0.2)]:
            out.append(HistoricalBar(
                instrument="GC", contract="GCG5", event_time=t0 + timedelta(days=d, minutes=minute),
                open=close, high=close + 1, low=close - 1, close=close, volume=10,
                quality_state=QualityState.VERIFIED, source_id="TEST", roll_method=RollMethod.RAW_CONTRACT,
            ))
    return out


def _book(signal_time):
    trade = EvidenceTrade(
        contract="GCG5", horizon_minutes=60, candidate_id="c1", signal_time=signal_time,
        direction="LONG", first_touch="TARGET", bars_to_first_touch=1, net_pnl_price=1.0, resolved=True,
    )
    cells = []
    for h in (5, 15, 30, 60):
        t = EvidenceTrade(
            contract="GCG5", horizon_minutes=h, candidate_id="c1", signal_time=signal_time,
            direction="LONG", first_touch="TARGET", bars_to_first_touch=1, net_pnl_price=1.0, resolved=True,
        )
        cells.append(EvidenceBookCell("GCG5", h, "OK", 1, 1, 1, (t,), "d", "c", f"r{h}"))
    return EvidenceBook("P", ("GCG5",), (5, 15, 30, 60), tuple(cells))


def test_labels_session_volatility_and_visible_macro_window():
    bars = _bars()
    signal = datetime(2025, 1, 30, 14, 0, tzinfo=timezone.utc)
    event = MacroEvent(
        event_time=signal + timedelta(minutes=10),
        known_at=signal - timedelta(days=1),
        category="CPI",
    )
    labels = build_regime_labels(bars=bars, book=_book(signal), macro_events=(event,))
    assert labels["c1"][0] == "NY_AM"
    assert labels["c1"][1] in {"VOL_LOW", "VOL_NORMAL", "VOL_HIGH"}
    assert "MACRO_WINDOW" in labels["c1"]
    assert "MACRO_CPI" in labels["c1"]


def test_future_unknown_macro_event_cannot_label_candidate():
    bars = _bars()
    signal = datetime(2025, 1, 30, 14, 0, tzinfo=timezone.utc)
    # Invalid provenance itself fails closed: a scheduled event cannot become known after event time.
    with pytest.raises(ValueError, match="known after"):
        MacroEvent(signal + timedelta(minutes=10), signal + timedelta(minutes=20), "CPI")


def test_macro_outside_locked_window_is_no_macro_window():
    bars = _bars()
    signal = datetime(2025, 1, 30, 14, 0, tzinfo=timezone.utc)
    event = MacroEvent(signal + timedelta(minutes=45), signal - timedelta(days=1), "NFP")
    labels = build_regime_labels(bars=bars, book=_book(signal), macro_events=(event,))
    assert "NO_MACRO_WINDOW" in labels["c1"]


def test_insufficient_volatility_history_fails_closed():
    bars = _bars(days=10)
    signal = datetime(2025, 1, 10, 14, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="insufficient completed-day history"):
        build_regime_labels(bars=bars, book=_book(signal), macro_events=())
