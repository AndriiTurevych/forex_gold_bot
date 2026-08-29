"""Deterministic trade-candidate construction for EXP-0001.

Converts an accepted EXP-0001 signal into the strategy-agnostic backtest runner
format. Stop is placed beyond the swept extreme; target is the supplied opposing
liquidity level. No RR optimization or post-result parameter tuning is performed.
"""
from __future__ import annotations

from math import isfinite

from gold_cio_v9.backtest.runner import TradeCandidate
from gold_cio_v9.experiments.exp0001_signal import EXP0001Signal


def swept_extreme(signal: EXP0001Signal, *, sweep_depth: float) -> float:
    if not isfinite(sweep_depth) or sweep_depth <= 0:
        raise ValueError("sweep_depth must be finite and positive")
    if signal.swept_side == "SSL":
        return signal.swept_level - sweep_depth
    if signal.swept_side == "BSL":
        return signal.swept_level + sweep_depth
    raise ValueError("swept_side must be SSL or BSL")


def build_trade_candidate(
    *,
    signal: EXP0001Signal,
    signal_index: int,
    sweep_depth: float,
    opposing_liquidity: float,
    horizon_bars: int,
    candidate_id: str,
) -> TradeCandidate:
    """Create a fail-closed candidate using locked structural geometry.

    ``horizon_bars`` is retained in the call signature for compatibility with the
    locked EXP-0001 layers, but EXP-0001 preregistration defines wall-clock minute
    horizons. Therefore the same positive value is persisted as ``horizon_minutes``
    and the backtest runner labels by elapsed time, not by number of observed bars.
    """
    if not isfinite(opposing_liquidity):
        raise ValueError("opposing_liquidity must be finite")
    if horizon_bars <= 0:
        raise ValueError("horizon must be positive")
    stop = swept_extreme(signal, sweep_depth=sweep_depth)
    entry = signal.entry_price
    if signal.direction == "LONG":
        if opposing_liquidity <= entry:
            raise ValueError("LONG opposing liquidity must be above entry")
        target = opposing_liquidity
    elif signal.direction == "SHORT":
        if opposing_liquidity >= entry:
            raise ValueError("SHORT opposing liquidity must be below entry")
        target = opposing_liquidity
    else:
        raise ValueError("direction must be LONG or SHORT")
    return TradeCandidate(
        candidate_id=candidate_id,
        signal_index=signal_index,
        direction=signal.direction,
        entry=entry,
        stop=stop,
        target=target,
        horizon_bars=horizon_bars,
        horizon_minutes=horizon_bars,
    )
