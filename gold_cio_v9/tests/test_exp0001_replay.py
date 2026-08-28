from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.experiments.exp0001_replay import ReplaySetup, build_replay_candidates
from gold_cio_v9.experiments.exp0001_signal import FVGZone, TimedStructure, TimedSweep
from gold_cio_v9.ict_engine.features import Bar, Sweep
from gold_cio_v9.ict_engine.structure import StructureEvent


def _setup(setup_id="s1", signal_index=10, htf=True):
    t0 = datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc)
    return ReplaySetup(
        setup_id=setup_id,
        signal_index=signal_index,
        htf_location_ok=htf,
        sweep=TimedSweep(t0, Sweep("SSL", 100.0, 1.0)),
        structure=TimedStructure(
            t0 + timedelta(minutes=1),
            StructureEvent("MSS", "BULLISH", 101.0, 102.0, 1.0),
        ),
        zone=FVGZone(t0 + timedelta(minutes=2), 101.0, 102.0, "BULLISH"),
        retest_time=t0 + timedelta(minutes=3),
        retest_bar=Bar("2026-01-01T13:33:00Z", 102.5, 103.0, 101.5, 102.0),
        sweep_depth=1.0,
        opposing_liquidity=106.0,
        horizon_bars=60,
    )


def test_locked_setup_emits_candidate():
    candidates = build_replay_candidates([_setup()])
    assert len(candidates) == 1
    c = candidates[0]
    assert c.candidate_id == "s1"
    assert c.signal_index == 10
    assert c.direction == "LONG"
    assert c.entry == 102.0
    assert c.stop == 99.0
    assert c.target == 106.0


def test_rejected_signal_is_skipped_not_repaired():
    assert build_replay_candidates([_setup(htf=False)]) == ()


def test_duplicate_setup_id_fails_closed():
    with pytest.raises(ValueError, match="duplicate setup_id"):
        build_replay_candidates([_setup("dup", 10), _setup("dup", 20)])


def test_non_monotonic_signal_index_fails_closed():
    with pytest.raises(ValueError, match="strictly increasing"):
        build_replay_candidates([_setup("a", 20), _setup("b", 20)])


def test_invalid_candidate_geometry_fails_closed():
    bad = _setup()
    bad = ReplaySetup(**{**bad.__dict__, "opposing_liquidity": 101.0})
    with pytest.raises(ValueError, match="above entry"):
        build_replay_candidates([bad])
