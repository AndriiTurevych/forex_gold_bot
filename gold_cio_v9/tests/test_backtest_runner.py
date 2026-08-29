from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.backtest.costs import CostAssumptions
from gold_cio_v9.backtest.runner import TradeCandidate, run_backtest
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.validation.ledger import EvidenceLedger
from gold_cio_v9.validation.metrics import removal_top_trades_expectancy, top_fraction_pnl_share, trade_metrics

UTC = timezone.utc


def _bars(n=12):
    t0 = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
    out = []
    px = 4500.0
    for i in range(n):
        close = px + (2.0 if i % 2 == 0 else -1.0)
        high = max(px, close) + 1.0
        low = min(px, close) - 1.0
        out.append(HistoricalBar("GC", "GCG26", t0 + timedelta(minutes=i), px, high, low, close, 1000.0, QualityState.VERIFIED, "fixture", RollMethod.RAW_CONTRACT, False))
        px = close
    return out


def test_runner_is_deterministic_and_hashes_lineage():
    bars = _bars()
    c = [TradeCandidate("c1", 1, "LONG", 4501.0, 4498.0, 4507.0, 5)]
    costs = CostAssumptions(0.1, 0.05, 0.05)
    r1 = run_backtest(bars=bars, candidates=c, instrument="GC", costs=costs)
    r2 = run_backtest(bars=bars, candidates=c, instrument="GC", costs=costs)
    assert r1.data_snapshot_hash == r2.data_snapshot_hash
    assert r1.candidate_snapshot_hash == r2.candidate_snapshot_hash
    assert r1.result_hash == r2.result_hash
    assert r1.trades == r2.trades


def test_clock_horizon_does_not_extend_across_missing_minutes():
    t0 = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
    bars = [
        HistoricalBar("GC", "GCG26", t0, 100, 101, 99, 100, 10, QualityState.VERIFIED, "fixture", RollMethod.RAW_CONTRACT, False),
        HistoricalBar("GC", "GCG26", t0 + timedelta(minutes=1), 100, 101, 99, 100, 10, QualityState.VERIFIED, "fixture", RollMethod.RAW_CONTRACT, False),
        # no bars at +2..+9; a target touch at +10 must not enter a 5-minute label
        HistoricalBar("GC", "GCG26", t0 + timedelta(minutes=10), 100, 110, 99, 109, 10, QualityState.VERIFIED, "fixture", RollMethod.RAW_CONTRACT, False),
    ]
    c = [TradeCandidate("clock", 0, "LONG", 100, 95, 105, 5, horizon_minutes=5)]
    with pytest.raises(ValueError, match="no future bars within clock horizon"):
        # only +1 is inside horizon, so actually there is one future bar; this should run
        run_backtest(bars=bars[:1] + bars[2:], candidates=c, instrument="GC", costs=CostAssumptions(0,0,0))

    r = run_backtest(bars=bars, candidates=c, instrument="GC", costs=CostAssumptions(0,0,0))
    assert r.trades[0].first_touch != "TARGET"


def test_metrics_and_concentration_helpers():
    values = [2.0, 1.0, -1.0, -0.5, 0.5, 1.5, -0.25, 0.75, 1.25, -0.75, 0.8, 0.6, -0.4, 0.9, 1.1, -0.6, 0.7, 0.4, -0.3, 0.5]
    m = trade_metrics(values)
    assert m.count == len(values)
    assert m.expectancy > 0
    assert m.profit_factor > 1
    assert 0 < top_fraction_pnl_share(values) <= 1
    assert isinstance(removal_top_trades_expectancy(values), float)


def test_evidence_ledger_is_append_only(tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    ledger.append(experiment_id="EXP-0001", trial_id="t1", git_commit="abc", data_snapshot_hash="d", candidate_snapshot_hash="c", result_hash="r", config_hash="cfg", verdict="REJECT", metrics={"pf": 1.0}, failed_gates=("OOS_PROFIT_FACTOR",))
    ledger.append(experiment_id="EXP-0001", trial_id="t2", git_commit="def", data_snapshot_hash="d2", candidate_snapshot_hash="c2", result_hash="r2", config_hash="cfg2", verdict="ACCEPT", metrics={"pf": 1.4}, failed_gates=())
    rows = ledger.read_all()
    assert len(rows) == 2
    assert rows[0]["verdict"] == "REJECT"
    assert rows[1]["verdict"] == "ACCEPT"
    assert rows[0]["record_hash"] != rows[1]["record_hash"]
