from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from gold_cio_v9.forward_v4 import (
    EXPERIMENT, HORIZONS, MINUTE, index_bars, next_minute, pending_contracts,
    record_decision, settle, verified_rows,
)
from gold_cio_v9.shadow.ledger import HashChainLedger
from scripts import forward_v4_cycle as cycle

NOW = datetime(2026, 9, 7, 12, 0, 20, tzinfo=timezone.utc)


def bar(start, contract="GCZ6", open=100., close=102.):
    return SimpleNamespace(event_time=start, contract=contract, open=open, close=close,
                           high=max(open, close) + 1, low=min(open, close) - 1, volume=10.)


def decision(ledger, **kwargs):
    options = dict(
        ledger=ledger, candidate={"contract": "GCZ6", "direction": "LONG", "candidate_id": "unstable-index",
                                  "structural_signal_time": NOW.replace(second=0) - MINUTE},
        bars=[bar(NOW.replace(second=0) - MINUTE)], front_contract="GCZ6", received_at=NOW,
        decision_at=NOW, snapshot_hash="snapshot-1", engine_commit="engine", candidate_hash="candidate-hash",
    )
    options.update(kwargs)
    return record_decision(**options)["payload"]


@pytest.fixture
def ledger(tmp_path):
    return HashChainLedger(tmp_path / "v4.jsonl")


def test_decision_is_not_fill_and_future_snapshot_required(ledger):
    p = decision(ledger)
    assert p["action"] == "BUY" and p["entry_price"] is None
    assert p["execution_allowed"] is False
    assert datetime.fromisoformat(p["fill_target_time"]) == next_minute(NOW)
    assert settle(ledger=ledger, bars=[bar(next_minute(NOW))], received_at=NOW, snapshot_hash="s") == 0
    assert len(verified_rows(ledger)) == 1


@pytest.mark.parametrize("direction,sign", [("LONG", 1), ("SHORT", -1)])
def test_fill_and_exact_close_horizons_and_idempotence(ledger, direction, sign):
    p = decision(ledger, candidate={"contract": "GCZ6", "direction": direction,
                                    "structural_signal_time": NOW.replace(second=0) - MINUTE})
    target = next_minute(NOW)
    bars = [bar(target, open=110.)] + [bar(target + (h - 1) * MINUTE, close=110. + h) for h in HORIZONS]
    observed = target + 61 * MINUTE
    assert settle(ledger=ledger, bars=bars, received_at=observed, snapshot_hash="s2") == 5
    rows = verified_rows(ledger)
    assert rows[1]["payload"]["entry_price"] == 110.
    for row, h in zip(rows[2:], HORIZONS):
        o = row["payload"]
        assert datetime.fromisoformat(o["exit_time"]) == target + h * MINUTE
        assert o["net_price"] == pytest.approx(sign * h - .35)
    assert settle(ledger=ledger, bars=bars, received_at=observed, snapshot_hash="s2") == 0
    assert not pending_contracts(ledger)
    assert p["entry_price"] is None


def test_missing_fill_cannot_move_to_next_bar_or_reappear_after_deadline(ledger):
    decision(ledger)
    target = next_minute(NOW)
    assert settle(ledger=ledger, bars=[bar(target + MINUTE)], received_at=target + 3 * MINUTE, snapshot_hash="s") == 0
    settle(ledger=ledger, bars=[bar(target)], received_at=target + timedelta(hours=25), snapshot_hash="late")
    assert verified_rows(ledger)[-1]["event_type"] == "FILL_MISSING"
    assert not pending_contracts(ledger)
    assert settle(ledger=ledger, bars=[bar(target)], received_at=target + timedelta(hours=26), snapshot_hash="later") == 0


def test_missing_exit_cannot_use_next_session_and_remains_pending_until_closed(ledger):
    decision(ledger)
    target = next_minute(NOW)
    settle(ledger=ledger, bars=[bar(target), bar(target + 59 * MINUTE)],
           received_at=target + 61 * MINUTE, snapshot_hash="s")
    assert pending_contracts(ledger) == {"GCZ6"}  # Primary done, secondary gaps still pending.
    settle(ledger=ledger, bars=[bar(target + timedelta(days=1))],
           received_at=target + timedelta(hours=26), snapshot_hash="next-session")
    rows = verified_rows(ledger)
    assert len([r for r in rows if r["event_type"] == "OUTCOME"]) == 1
    assert len([r for r in rows if r["event_type"] == "OUTCOME_MISSING"]) == 3
    assert not pending_contracts(ledger)


def test_incomplete_future_and_malformed_data(ledger):
    assert not index_bars([bar(next_minute(NOW))], NOW)
    with pytest.raises(ValueError, match="INVALID_OHLC"):
        index_bars([bar(NOW.replace(second=0) - MINUTE, close=float("nan"))], NOW)
    b = bar(NOW.replace(second=0) - MINUTE)
    with pytest.raises(ValueError, match="DUPLICATE_BAR"):
        index_bars([b, b], NOW)
    with pytest.raises(ValueError, match="NAIVE_TIMESTAMP"):
        index_bars([b], NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="DECISION_BEFORE_RECEIPT"):
        decision(ledger, decision_at=NOW - MINUTE)


def test_freshness_uses_decision_clock_not_acquisition_start(ledger):
    assert decision(ledger, decision_at=NOW + 21 * MINUTE)["reason"] == "STALE_DATA_VETO"


def test_late_decision_cannot_retroactively_reserve_fill(ledger):
    p = decision(ledger, commit_clock=lambda: NOW + 2 * MINUTE)
    assert p["reason"] == "DECISION_PERSISTENCE_WINDOW_MISSED"
    assert p["action"] == "ABSTAIN" and p["fill_target_time"] is None


def test_candidate_only_known_at_close(ledger):
    candidate = {"contract": "GCZ6", "direction": "LONG", "structural_signal_time": NOW.replace(second=0)}
    assert decision(ledger, candidate=candidate)["reason"] == "FUTURE_CANDIDATE_VETO"


def test_event_identity_ignores_rolling_index_and_blocks_overlap(ledger):
    first = decision(ledger)
    changed_id = {"contract": "GCZ6", "direction": "LONG", "candidate_id": "another-index",
                  "structural_signal_time": NOW.replace(second=0) - MINUTE}
    duplicate = decision(ledger, candidate=changed_id)
    assert duplicate["reason"] == "DUPLICATE_SIGNAL" and duplicate["signal_id"] == first["signal_id"]
    changed_id["structural_signal_time"] -= MINUTE
    overlap = decision(ledger, candidate=changed_id,
                       bars=[bar(NOW.replace(second=0) - MINUTE), bar(NOW.replace(second=0) - 2 * MINUTE)])
    assert overlap["reason"] == "OVERLAPPING_GC_EXPOSURE"


def test_never_restore_another_experiment(ledger):
    ledger.append("DECISION", {"experiment_id": "EXP-0003"})
    with pytest.raises(ValueError, match="EXPERIMENT_LEDGER_MISMATCH"):
        pending_contracts(ledger)


def test_collector_fetches_pending_contract_after_roll_and_freezes_closed_bars(ledger, tmp_path, monkeypatch):
    decision(ledger)
    monkeypatch.setattr(cycle, "select_front", lambda api, now: ("GCG7", "2026-09-04", 100))
    requests = []

    class API:
        def pages(self, path, params):
            requests.append((path, params))
            return [{"results": [{"window_start": int(t.timestamp()) * 1_000_000_000,
                                   "open": 100, "high": 103, "low": 99, "close": 102, "volume": 1}
                                  for t in (NOW.replace(second=0) - MINUTE, NOW.replace(second=0))]}]

    meta = cycle.collect(API(), ledger, NOW, tmp_path / "data", clock=lambda: NOW + 2 * MINUTE)
    assert meta["requested_contracts"] == ["GCG7", "GCZ6"]
    assert meta["bars"] == 2  # The interval incomplete at request start stays excluded.
    assert meta["received_at"] == (NOW + 2 * MINUTE).isoformat()
    assert all(isinstance(params["window_start.gte"], int) for _, params in requests)


def test_cycle_records_clock_after_feature_processing(ledger, tmp_path, monkeypatch):
    import json
    from hashlib import sha256
    t = NOW.replace(second=0) - MINUTE
    path = tmp_path / "bars.jsonl"
    path.write_text(json.dumps({"instrument": "GC", "contract": "GCZ6", "event_time": t.isoformat(),
                               "open": 100, "high": 103, "low": 99, "close": 102, "volume": 1,
                               "quality_state": "VERIFIED", "source_id": "test", "roll_method": "RAW_CONTRACT",
                               "is_roll_window": False}) + "\n")
    processed = []
    def build(bars):
        processed.append(True)
        return {"candidates": [], "candidate_windows_hash": "c"}
    def clock():
        assert processed
        return NOW + 2 * MINUTE
    monkeypatch.setattr(cycle, "build_windows", build)
    metadata = {"received_at": NOW.isoformat(), "contract": "GCZ6", "snapshot_hash": sha256(path.read_bytes()).hexdigest()}
    cycle.run_cycle(ledger=ledger, bars_path=path, metadata=metadata, engine_commit="test", clock=clock)
    assert verified_rows(ledger)[-1]["payload"]["decision_time"] == (NOW + 2 * MINUTE).isoformat()
    metadata["snapshot_hash"] = "tampered"
    with pytest.raises(ValueError, match="SNAPSHOT_HASH_MISMATCH"):
        cycle.run_cycle(ledger=ledger, bars_path=path, metadata=metadata, engine_commit="test", clock=clock)
