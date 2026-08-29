"""Frozen causal baseline inputs for preregistered EXP-0001.

This module closes the last raw-bars-to-strategy-input gap without using outcomes.
Rules are deterministic and point-in-time:
- prior trend is inferred only from already-confirmed swing structure;
- HTF location permission uses the completed prior UTC day dealing range midpoint;
- LONG is permitted only in discount, SHORT only in premium.

No optimization, P&L feedback, future bars, current-day completed range, or outcome
labels are used here. Changes after evidence observation require a new policy ID.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from gold_cio_v9.data.governance import HistoricalBar
from gold_cio_v9.ict_engine.causal_context import build_causal_context, confirm_swings


POLICY_ID = "EXP-0001-BASELINE-INPUTS-V1"


@dataclass(frozen=True)
class DirectionalPermission:
    long: bool
    short: bool

    def allows(self, direction: str) -> bool:
        if direction == "LONG":
            return self.long
        if direction == "SHORT":
            return self.short
        raise ValueError(f"invalid direction: {direction!r}")


@dataclass(frozen=True)
class CausalInputState:
    prior_trend_by_index: Mapping[int, str]
    htf_permission_by_index: Mapping[int, DirectionalPermission]


def _causal_trend_by_index(
    bars: Sequence[HistoricalBar],
    *,
    swing_left_bars: int,
    swing_right_bars: int,
) -> dict[int, str]:
    """Infer trend from the two latest visible confirmed highs and lows.

    BULLISH requires both a higher confirmed high and higher confirmed low.
    BEARISH requires both a lower confirmed high and lower confirmed low.
    Mixed/insufficient structure is intentionally left unclassified.
    """
    swings = confirm_swings(
        bars,
        left_bars=swing_left_bars,
        right_bars=swing_right_bars,
    )
    out: dict[int, str] = {}
    for i, bar in enumerate(bars):
        visible = [s for s in swings if s.available_time <= bar.event_time]
        highs = [s for s in visible if s.kind == "HIGH"]
        lows = [s for s in visible if s.kind == "LOW"]
        if len(highs) < 2 or len(lows) < 2:
            continue
        h1, h2 = highs[-2], highs[-1]
        l1, l2 = lows[-2], lows[-1]
        if h2.price > h1.price and l2.price > l1.price:
            out[i] = "BULLISH"
        elif h2.price < h1.price and l2.price < l1.price:
            out[i] = "BEARISH"
    return out


def build_exp0001_causal_inputs(
    bars: Sequence[HistoricalBar],
    *,
    atr_period: int,
    swing_left_bars: int,
    swing_right_bars: int,
) -> CausalInputState:
    """Materialize frozen trend and directional HTF-location inputs.

    Prior-day high/low come from ``build_causal_context`` and therefore become
    visible only after that UTC day is complete. Permission is evaluated at the
    current bar close against the prior completed day's midpoint:
    - close <= midpoint -> LONG allowed, SHORT blocked;
    - close >= midpoint -> SHORT allowed, LONG blocked;
    - exact midpoint permits both directions deterministically.
    """
    materialized = tuple(bars)
    if not materialized:
        raise ValueError("bars are required")
    causal = build_causal_context(
        materialized,
        atr_period=atr_period,
        swing_left_bars=swing_left_bars,
        swing_right_bars=swing_right_bars,
    )
    trends = _causal_trend_by_index(
        materialized,
        swing_left_bars=swing_left_bars,
        swing_right_bars=swing_right_bars,
    )
    permissions: dict[int, DirectionalPermission] = {}
    for c in causal:
        if c.prior_day_high is None or c.prior_day_low is None:
            continue
        if c.prior_day_high <= c.prior_day_low:
            raise ValueError("invalid prior-day dealing range")
        midpoint = (c.prior_day_high + c.prior_day_low) / 2.0
        close = materialized[c.index].close
        permissions[c.index] = DirectionalPermission(
            long=close <= midpoint,
            short=close >= midpoint,
        )
    return CausalInputState(trends, permissions)
