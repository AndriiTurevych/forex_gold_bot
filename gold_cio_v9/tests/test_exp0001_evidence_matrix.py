from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import gold_cio_v9.experiments.exp0001_evidence_matrix as matrix
from gold_cio_v9.backtest.costs import CostAssumptions
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod


def _bar(i, contract="GCQ5", roll=False):
    t = datetime(2025, 6, 2, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=i)
    return HistoricalBar(
        instrument="GC", contract=contract, event_time=t,
        open=100, high=101, low=99, close=100, volume=10,
        quality_state=QualityState.VERIFIED, source_id="TEST",
        roll_method=RollMethod.RAW_CONTRACT, is_roll_window=roll,
    )


def _costs():
    return CostAssumptions(0.1, 0.1, 0.1)


def test_matrix_runs_every_precommitted_horizon_for_every_contract(monkeypatch):
    bars = [_bar(0), _bar(1), _bar(2, "GCU5", roll=True), _bar(3, "GCU5")]
    calls = []

    def fake_pipeline(*, bars, config, costs):
        calls.append((bars[0].contract, config.horizon_bars, tuple(b.is_roll_window for b in bars)))
        bt = SimpleNamespace(trades=(1, 2), result_hash=f"{bars[0].contract}-{config.horizon_bars}")
        return SimpleNamespace(context_points=10, stream_events=3, replay_setups=2, backtest=bt)

    monkeypatch.setattr(matrix, "run_exp0001_pipeline", fake_pipeline)
    result = matrix.run_exp0001_evidence_matrix(bars=bars, costs=_costs())

    assert result.horizons_minutes == (5, 15, 30, 60)
    assert result.contracts == ("GCQ5", "GCU5")
    assert len(result.rows) == 8
    assert {(r.contract, r.horizon_minutes) for r in result.rows} == {
        (c, h) for c in ("GCQ5", "GCU5") for h in (5, 15, 30, 60)
    }
    assert all(not any(flags) for _, _, flags in calls)


def test_no_setup_is_recorded_not_dropped(monkeypatch):
    monkeypatch.setattr(
        matrix,
        "run_exp0001_pipeline",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("no complete causal EXP-0001 replay setups")),
    )
    result = matrix.run_exp0001_evidence_matrix(bars=[_bar(0), _bar(1)], costs=_costs())
    assert len(result.rows) == 4
    assert all(r.status == "NO_SETUPS" and r.trade_count == 0 for r in result.rows)


def test_unexpected_pipeline_error_is_not_reclassified(monkeypatch):
    monkeypatch.setattr(
        matrix,
        "run_exp0001_pipeline",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("DATA_CORRUPTION")),
    )
    with pytest.raises(ValueError, match="DATA_CORRUPTION"):
        matrix.run_exp0001_evidence_matrix(bars=[_bar(0), _bar(1)], costs=_costs())


def test_contract_reentry_and_empty_roll_segment_fail_closed():
    with pytest.raises(ValueError, match="re-entry"):
        matrix.split_raw_contract_segments([_bar(0, "GCQ5"), _bar(1, "GCU5"), _bar(2, "GCQ5")])
    with pytest.raises(ValueError, match="only roll-window"):
        matrix.split_raw_contract_segments([_bar(0, "GCQ5", roll=True)])
