import pytest

from gold_cio_v9.data.governance import QualityState, RollMethod
from gold_cio_v9.data.massive_gc import SOURCE_ID, parse_massive_gc_aggs


def _row(ts=1785708000000000000, ticker="GCU6"):
    return {
        "ticker": ticker,
        "window_start": ts,
        "open": 4086.2,
        "high": 4094.9,
        "low": 4083.6,
        "close": 4084.4,
        "volume": 18,
    }


def test_massive_gc_rows_become_raw_verified_contract_bars():
    bars = parse_massive_gc_aggs([_row()])
    assert len(bars) == 1
    bar = bars[0]
    assert bar.instrument == "GC"
    assert bar.contract == "GCU6"
    assert bar.quality_state is QualityState.VERIFIED
    assert bar.roll_method is RollMethod.RAW_CONTRACT
    assert bar.source_id == SOURCE_ID
    assert bar.event_time.tzinfo is not None


def test_adapter_never_synthesizes_missing_minutes():
    rows = [_row(), _row(ts=1785708120000000000)]
    bars = parse_massive_gc_aggs(rows)
    assert len(bars) == 2
    assert int((bars[1].event_time - bars[0].event_time).total_seconds()) == 120


def test_duplicate_contract_timestamp_fails_closed():
    with pytest.raises(ValueError, match="duplicate aggregate bar"):
        parse_massive_gc_aggs([_row(), _row()])


def test_spread_ticker_is_rejected():
    with pytest.raises(ValueError, match="invalid GC single-contract ticker"):
        parse_massive_gc_aggs([_row(ticker="GCU6-GCZ6")])
