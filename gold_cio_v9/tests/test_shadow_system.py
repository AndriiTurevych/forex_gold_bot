from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.shadow.engine import ShadowCandidate, ShadowFeed, decide_shadow
from gold_cio_v9.shadow.ledger import HashChainLedger
from gold_cio_v9.shadow.outcomes import settle_matured
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from scripts.acquire_shadow_massive import candidate_tickers


NOW = datetime(2026, 9, 6, 18, 0, tzinfo=timezone.utc)


def _feed(age_minutes=2):
    return ShadowFeed(NOW, NOW - timedelta(minutes=age_minutes), 3600.0, "data-hash")


def _candidate(age_minutes=3, direction="LONG"):
    return ShadowCandidate("candidate-1", "GCZ6", direction, NOW - timedelta(minutes=age_minutes))


def test_fresh_candidate_emits_shadow_buy_without_execution_permission():
    decision = decide_shadow(candidate=_candidate(), feed=_feed(), strategy_version="EXP-0003", seen_signal_ids=set())
    assert decision.action == "BUY"
    assert decision.reason == "SHADOW_SIGNAL_ONLY"
    assert decision.execution_allowed is False


def test_stale_feed_forces_abstain():
    decision = decide_shadow(candidate=_candidate(), feed=_feed(21), strategy_version="EXP-0003", seen_signal_ids=set())
    assert (decision.action, decision.reason) == ("ABSTAIN", "STALE_DATA_VETO")


def test_shadow_engine_cannot_enable_real_orders():
    with pytest.raises(RuntimeError, match="LIVE_ORDERS_FORBIDDEN"):
        decide_shadow(candidate=_candidate(), feed=_feed(), strategy_version="EXP-0003", seen_signal_ids=set(), real_orders_enabled=True)


def test_hash_chain_detects_mutation(tmp_path):
    ledger = HashChainLedger(tmp_path / "shadow.jsonl")
    ledger.append("DECISION", {"action": "ABSTAIN"})
    ledger.append("HEARTBEAT", {"ok": True})
    assert len(ledger.read_verified()) == 2
    text = ledger.path.read_text().replace('"ok":true', '"ok":false')
    ledger.path.write_text(text)
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        ledger.read_verified()


def test_matured_outcomes_append_without_mutating_decision(tmp_path):
    ledger = HashChainLedger(tmp_path / "shadow.jsonl")
    ledger.append("DECISION", {
        "action": "BUY", "signal_id": "sig", "contract": "GCZ6",
        "decision_time": NOW.isoformat(), "entry_price": 3600.0,
    })
    bars = tuple(HistoricalBar(
        "GC", "GCZ6", NOW + timedelta(minutes=m), 3600.0, 3610.0, 3590.0,
        3600.0 + m / 10, 1.0, QualityState.VERIFIED, f"s{m}", RollMethod.RAW_CONTRACT,
    ) for m in (5, 15, 30, 60))
    assert settle_matured(ledger, bars) == 4
    rows = ledger.read_verified()
    assert rows[0]["event_type"] == "DECISION"
    assert [r["payload"]["horizon_minutes"] for r in rows[1:]] == [5, 15, 30, 60]


def test_front_candidate_universe_rolls_forward():
    tickers = candidate_tickers(datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert tickers[:2] == ("GCV6", "GCZ6")
    assert "GCG7" in tickers and "GCZ7" in tickers
