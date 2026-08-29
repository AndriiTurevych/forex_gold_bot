"""One-call causal orchestration for preregistered EXP-0001.

This module connects the tested causal layers and now derives the frozen baseline
trend/HTF inputs from raw bars. The evidence path therefore no longer accepts
caller-supplied discretionary trend or HTF-permission maps.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from gold_cio_v9.backtest.costs import CostAssumptions
from gold_cio_v9.backtest.runner import BacktestResult
from gold_cio_v9.data.governance import HistoricalBar
from gold_cio_v9.experiments.exp0001_backtest import run_exp0001_backtest
from gold_cio_v9.experiments.exp0001_inputs import build_exp0001_causal_inputs
from gold_cio_v9.experiments.exp0001_sequence import assemble_replay_setups
from gold_cio_v9.experiments.exp0001_stream import ContextPoint, build_event_stream
from gold_cio_v9.ict_engine.causal_context import build_causal_context


@dataclass(frozen=True)
class PipelineConfig:
    atr_period: int
    swing_left_bars: int
    swing_right_bars: int
    horizon_bars: int

    def __post_init__(self) -> None:
        if min(self.atr_period, self.swing_left_bars, self.swing_right_bars, self.horizon_bars) <= 0:
            raise ValueError("pipeline configuration values must be positive")


@dataclass(frozen=True)
class PipelineResult:
    context_points: int
    stream_events: int
    replay_setups: int
    backtest: BacktestResult


def _materialize_context_points(
    bars: Sequence[HistoricalBar],
    *,
    config: PipelineConfig,
    prior_trend_by_index,
) -> tuple[ContextPoint, ...]:
    causal = build_causal_context(
        bars,
        atr_period=config.atr_period,
        swing_left_bars=config.swing_left_bars,
        swing_right_bars=config.swing_right_bars,
    )
    points: list[ContextPoint] = []
    for c in causal:
        if (
            c.atr_prior is None
            or c.prior_day_high is None
            or c.prior_day_low is None
            or c.latest_swing_high is None
            or c.latest_swing_low is None
        ):
            continue
        trend = prior_trend_by_index.get(c.index)
        if trend is None:
            continue
        if trend not in {"BULLISH", "BEARISH"}:
            raise ValueError(f"invalid prior trend at index {c.index}")
        points.append(
            ContextPoint(
                index=c.index,
                reference_high=c.prior_day_high,
                reference_low=c.prior_day_low,
                prior_swing_high=c.latest_swing_high.price,
                prior_swing_low=c.latest_swing_low.price,
                prior_trend=trend,
                atr=c.atr_prior,
            )
        )
    return tuple(points)


def run_exp0001_pipeline(
    *,
    bars: Sequence[HistoricalBar],
    config: PipelineConfig,
    costs: CostAssumptions,
) -> PipelineResult:
    """Run raw bars -> frozen PIT inputs -> events -> setups -> deterministic backtest.

    No caller-supplied trend or HTF permission is accepted on the evidence path.
    The function remains fail-closed if causal information is insufficient.
    """
    materialized = tuple(bars)
    if not materialized:
        raise ValueError("bars are required")

    inputs = build_exp0001_causal_inputs(
        materialized,
        atr_period=config.atr_period,
        swing_left_bars=config.swing_left_bars,
        swing_right_bars=config.swing_right_bars,
    )
    context = _materialize_context_points(
        materialized,
        config=config,
        prior_trend_by_index=inputs.prior_trend_by_index,
    )
    if not context:
        raise ValueError("no complete point-in-time context available")

    events = build_event_stream(materialized, context)
    if not events:
        raise ValueError("no causal EXP-0001 events available")

    setups = assemble_replay_setups(
        bars=materialized,
        events=events,
        context=context,
        htf_permission=inputs.htf_permission_by_index,
        horizon_bars=config.horizon_bars,
    )
    if not setups:
        raise ValueError("no complete causal EXP-0001 replay setups")

    result = run_exp0001_backtest(bars=materialized, setups=setups, costs=costs)
    return PipelineResult(len(context), len(events), len(setups), result)
