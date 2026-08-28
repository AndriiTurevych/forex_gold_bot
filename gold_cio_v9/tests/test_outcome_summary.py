from gold_cio_v9.backtest.runner import BacktestResult, TradeResult
from gold_cio_v9.validation.outcome_summary import summarize_oos


def trade(cid: str, pnl: float, touch: str = "TARGET") -> TradeResult:
    return TradeResult(cid, 1, "LONG", touch, 1, 1.0, 0.2, 1.0, pnl, pnl)


def result(*trades: TradeResult) -> BacktestResult:
    return BacktestResult("GC", "data", "candidates", "result", tuple(trades))


def test_ambiguous_trade_is_excluded_from_realized_metrics():
    summary = summarize_oos(result(trade("a", 2.0), trade("b", -1.0, "STOP"), trade("c", float("nan"), "AMBIGUOUS")))
    assert summary.total_candidates == 3
    assert summary.resolved_trades == 2
    assert summary.ambiguous_trades == 1
    assert summary.ambiguity_rate == 1 / 3
    assert summary.metrics.count == 2
    assert summary.metrics.expectancy == 0.5


def test_concentration_and_top_trade_removal_are_reported():
    summary = summarize_oos(result(trade("a", 10.0), trade("b", 1.0), trade("c", -1.0, "STOP"), trade("d", -1.0, "STOP")))
    assert summary.top_5pct_positive_pnl_share == 10.0 / 11.0
    assert summary.expectancy_after_top_5pct_removal == -1.0 / 3.0


def test_no_resolved_trades_fails_closed():
    try:
        summarize_oos(result(trade("a", float("nan"), "AMBIGUOUS")))
    except ValueError as exc:
        assert "no resolved" in str(exc)
    else:
        raise AssertionError("expected fail-closed behavior")
