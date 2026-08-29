from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import gold_cio_v9.experiments.exp0001_pipeline as pipeline
from gold_cio_v9.backtest.costs import CostAssumptions
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.experiments.exp0001_inputs import CausalInputState, DirectionalPermission
from gold_cio_v9.ict_engine.pit_events import ConfirmedSwing


def _bar():
    return HistoricalBar(
        instrument="GC",
        contract="GCZ6",
        event_time=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        open=4000.0,
        high=4002.0,
        low=3998.0,
        close=4001.0,
        volume=10.0,
        quality_state=QualityState.VERIFIED,
        source_id="TEST",
        roll_method=RollMethod.RAW_CONTRACT,
    )


def _context():
    t = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    prior = datetime(2026, 8, 20, 11, 59, tzinfo=timezone.utc)
    sh = ConfirmedSwing("HIGH", 4010.0, prior, t, 1, 1)
    sl = ConfirmedSwing("LOW", 3990.0, prior, t, 1, 1)
    return SimpleNamespace(
        index=0,
        atr_prior=5.0,
        prior_day_high=4020.0,
        prior_day_low=3980.0,
        latest_swing_high=sh,
        latest_swing_low=sl,
    )


def _costs():
    return CostAssumptions(
        spread_price=0.1,
        commission_price_equivalent_round_turn=0.1,
        slippage_price_per_side=0.1,
    )


def test_pipeline_delegates_locked_layers_once(monkeypatch):
    bars = (_bar(),)
    cfg = pipeline.PipelineConfig(atr_period=14, swing_left_bars=2, swing_right_bars=2, horizon_bars=30)
    calls = []
    sentinel = object()

    monkeypatch.setattr(pipeline, "build_exp0001_causal_inputs", lambda *a, **k: CausalInputState({0: "BULLISH"}, {0: DirectionalPermission(True, False)}))
    monkeypatch.setattr(pipeline, "build_causal_context", lambda *a, **k: (_context(),))

    def stream(b, c):
        calls.append(("stream", b, c))
        return (SimpleNamespace(index=0),)

    def sequence(**kwargs):
        calls.append(("sequence", kwargs))
        return (SimpleNamespace(setup_id="S1"),)

    def backtest(**kwargs):
        calls.append(("backtest", kwargs))
        return sentinel

    monkeypatch.setattr(pipeline, "build_event_stream", stream)
    monkeypatch.setattr(pipeline, "assemble_replay_setups", sequence)
    monkeypatch.setattr(pipeline, "run_exp0001_backtest", backtest)

    out = pipeline.run_exp0001_pipeline(bars=bars, config=cfg, costs=_costs())

    assert out.context_points == 1
    assert out.stream_events == 1
    assert out.replay_setups == 1
    assert out.backtest is sentinel
    assert [x[0] for x in calls] == ["stream", "sequence", "backtest"]
    assert calls[1][1]["horizon_bars"] == 30
    assert calls[1][1]["htf_permission"] == {0: DirectionalPermission(True, False)}


def test_incomplete_context_fails_closed(monkeypatch):
    c = _context()
    monkeypatch.setattr(pipeline, "build_exp0001_causal_inputs", lambda *a, **k: CausalInputState({0: "BULLISH"}, {0: DirectionalPermission(True, False)}))
    monkeypatch.setattr(
        pipeline,
        "build_causal_context",
        lambda *a, **k: (SimpleNamespace(**{**c.__dict__, "atr_prior": None}),),
    )
    with pytest.raises(ValueError, match="no complete point-in-time context"):
        pipeline.run_exp0001_pipeline(
            bars=(_bar(),),
            config=pipeline.PipelineConfig(14, 2, 2, 30),
            costs=_costs(),
        )


def test_invalid_prior_trend_fails_closed(monkeypatch):
    monkeypatch.setattr(pipeline, "build_exp0001_causal_inputs", lambda *a, **k: CausalInputState({0: "SIDEWAYS"}, {0: DirectionalPermission(True, False)}))
    monkeypatch.setattr(pipeline, "build_causal_context", lambda *a, **k: (_context(),))
    with pytest.raises(ValueError, match="invalid prior trend"):
        pipeline.run_exp0001_pipeline(
            bars=(_bar(),),
            config=pipeline.PipelineConfig(14, 2, 2, 30),
            costs=_costs(),
        )


@pytest.mark.parametrize("values", [(0, 2, 2, 30), (14, 0, 2, 30), (14, 2, 0, 30), (14, 2, 2, 0)])
def test_pipeline_config_rejects_non_positive_values(values):
    with pytest.raises(ValueError, match="positive"):
        pipeline.PipelineConfig(*values)
