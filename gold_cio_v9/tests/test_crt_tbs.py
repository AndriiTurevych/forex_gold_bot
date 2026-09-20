from datetime import datetime, timedelta, timezone

from gold_cio_v9.live.crt_tbs import detect_crt_tbs
from gold_cio_v9.live.mt5_analysis import Candle


def _bars(start, minutes, rows):
    return [
        Candle(start + timedelta(minutes=minutes*i), *row)
        for i, row in enumerate(rows)
    ]


def test_h1_m5_long_failed_breakout_is_detected():
    start = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
    h1 = _bars(start, 60, [
        (100, 103, 99, 102),
        (102, 104, 100, 103),
    ])
    # 15+ bars provide ATR history; last trigger sweeps H1 low=100 and closes back inside.
    rows = [(101.5, 102.0, 101.0, 101.6)] * 15
    rows += [(100.4, 101.2, 99.7, 101.0)]
    m5 = _bars(start + timedelta(hours=2), 5, rows)
    m15 = _bars(start, 15, [(101.0, 102.0, 100.2, 101.5)] * 16)
    h4 = _bars(start - timedelta(hours=8), 240, [(99, 105, 98, 103), (103, 106, 100, 104)])

    result = detect_crt_tbs(h4=h4, h1=h1, m15=m15, m5=m5, min_rr_tp2=1.0)
    assert result is not None
    assert result.direction == "LONG"
    assert result.model == "H1_M5"
    assert result.swept_side == "LOW"
    assert result.stop < result.entry < result.tp2


def test_breakout_that_closes_outside_range_is_rejected():
    start = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
    h1 = _bars(start, 60, [(100, 103, 99, 102), (102, 104, 100, 103)])
    rows = [(101.5, 102.0, 101.0, 101.6)] * 15
    rows += [(100.4, 100.6, 99.7, 99.8)]  # close remains outside below 100
    m5 = _bars(start + timedelta(hours=2), 5, rows)
    m15 = _bars(start, 15, [(100, 101, 99.8, 100.5)] * 16)
    h4 = _bars(start - timedelta(hours=8), 240, [(99, 105, 98, 103), (103, 106, 100, 104)])

    assert detect_crt_tbs(h4=h4, h1=h1, m15=m15, m5=m5, min_rr_tp2=1.0) is None
