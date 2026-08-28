from datetime import datetime, timezone

import pytest

from gold_cio_v9.experiments.exp0001_candidates import build_trade_candidate, swept_extreme
from gold_cio_v9.experiments.exp0001_signal import EXP0001Signal


def _signal(direction="LONG", swept_side="SSL", entry=100.0, level=99.0):
    return EXP0001Signal(
        direction=direction,
        entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        entry_price=entry,
        swept_side=swept_side,
        swept_level=level,
        fvg_low=99.5,
        fvg_high=100.5,
        fvg_kind="FVG",
    )


def test_long_stop_is_beyond_swept_ssl_extreme_and_target_is_opposing_liquidity():
    s = _signal()
    c = build_trade_candidate(
        signal=s,
        signal_index=10,
        sweep_depth=0.5,
        opposing_liquidity=103.0,
        horizon_bars=60,
        candidate_id="x",
    )
    assert c.stop == 98.5
    assert c.entry == 100.0
    assert c.target == 103.0
    assert c.direction == "LONG"


def test_short_stop_is_beyond_swept_bsl_extreme():
    s = _signal(direction="SHORT", swept_side="BSL", entry=100.0, level=101.0)
    c = build_trade_candidate(
        signal=s,
        signal_index=11,
        sweep_depth=0.4,
        opposing_liquidity=97.0,
        horizon_bars=30,
        candidate_id="y",
    )
    assert c.stop == pytest.approx(101.4)
    assert c.target == 97.0


def test_wrong_side_target_fails_closed():
    with pytest.raises(ValueError):
        build_trade_candidate(
            signal=_signal(), signal_index=1, sweep_depth=0.5,
            opposing_liquidity=99.9, horizon_bars=60, candidate_id="bad"
        )


def test_nonpositive_sweep_depth_rejected():
    with pytest.raises(ValueError):
        swept_extreme(_signal(), sweep_depth=0.0)
