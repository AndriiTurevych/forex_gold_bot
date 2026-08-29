from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import gold_cio_v9.experiments.exp0001_evidence_book as book
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod


def _bars():
    t0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
    return [
        HistoricalBar(
            instrument="GC", contract="GCG6", event_time=t0 + timedelta(minutes=i),
            open=100, high=101, low=99, close=100, volume=10,
            quality_state=QualityState.VERIFIED, source_id="TEST",
            roll_method=RollMethod.RAW_CONTRACT,
        )
        for i in range(8)
    ]


def test_book_preserves_trade_time_identity_and_all_horizons(monkeypatch):
    bars = _bars()

    def fake_pipeline(*, bars, config, costs):
        trade = SimpleNamespace(
            candidate_id=f"c{config.horizon_bars}", signal_index=3, direction="LONG",
            first_touch="TARGET", bars_to_first_touch=2, net_pnl_price=1.5,
        )
        bt = SimpleNamespace(
            trades=(trade,), data_snapshot_hash="d", candidate_snapshot_hash="c",
            result_hash=f"r{config.horizon_bars}",
        )
        return SimpleNamespace(context_points=5, stream_events=4, replay_setups=1, backtest=bt)

    monkeypatch.setattr(book, "run_exp0001_pipeline", fake_pipeline)
    out = book.build_exp0001_evidence_book(bars=bars, costs=object())
    assert out.horizons_minutes == (5, 15, 30, 60)
    assert len(out.cells) == 4
    assert len(out.trades_for_horizon(60)) == 1
    t = out.trades_for_horizon(60)[0]
    assert t.signal_time == bars[3].event_time
    assert t.contract == "GCG6"
    assert t.resolved is True


def test_ambiguous_trade_is_retained_but_not_resolved(monkeypatch):
    bars = _bars()

    def fake_pipeline(*, bars, config, costs):
        trade = SimpleNamespace(
            candidate_id="amb", signal_index=2, direction="SHORT",
            first_touch="AMBIGUOUS", bars_to_first_touch=1, net_pnl_price=float("nan"),
        )
        bt = SimpleNamespace(trades=(trade,), data_snapshot_hash="d", candidate_snapshot_hash="c", result_hash="r")
        return SimpleNamespace(context_points=5, stream_events=4, replay_setups=1, backtest=bt)

    monkeypatch.setattr(book, "run_exp0001_pipeline", fake_pipeline)
    out = book.build_exp0001_evidence_book(bars=bars, costs=object())
    assert all(cell.trades[0].resolved is False for cell in out.cells)


def test_expected_no_setup_status_is_not_silently_dropped(monkeypatch):
    bars = _bars()
    monkeypatch.setattr(
        book, "run_exp0001_pipeline",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("no complete causal EXP-0001 replay setups")),
    )
    out = book.build_exp0001_evidence_book(bars=bars, costs=object())
    assert len(out.cells) == 4
    assert all(cell.status == "NO_SETUPS" and not cell.trades for cell in out.cells)
