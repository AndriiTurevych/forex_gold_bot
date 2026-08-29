from datetime import datetime, timezone
import json

import pytest

from gold_cio_v9.data.contract_master import build_gc_contract_master
from gold_cio_v9.data.dataset_manifest import build_gc_dataset_manifest
from gold_cio_v9.data.evidence_lineage import AcquisitionLineageManifest, RollDecisionLineage, compute_acquisition_lineage_hash
from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.validation.evidence_inputs import (
    load_acquisition_lineage_json,
    load_authoritative_bars_jsonl,
    load_contract_master_json,
    load_macro_calendar_json,
)
from gold_cio_v9.validation.exp0001_regimes import MacroEvent
from gold_cio_v9.validation.macro_calendar import build_macro_calendar_snapshot


def _bar_payload(ts="2025-06-02T12:00:00+00:00"):
    return {
        "instrument": "GC", "contract": "GCQ5", "event_time": ts,
        "open": 3300.0, "high": 3301.0, "low": 3299.0, "close": 3300.5, "volume": 10.0,
        "quality_state": "VERIFIED", "source_id": "massive:real", "roll_method": "RAW_CONTRACT",
        "is_roll_window": False,
    }


def test_authoritative_bar_loader_preserves_identity(tmp_path):
    p = tmp_path / "bars.jsonl"
    p.write_text(json.dumps(_bar_payload()) + "\n" + json.dumps(_bar_payload("2025-06-02T12:01:00+00:00")) + "\n")
    bars = load_authoritative_bars_jsonl(p)
    assert len(bars) == 2
    assert bars[0].contract == "GCQ5"
    assert bars[0].source_id == "massive:real"


def test_bar_loader_rejects_nonchronological_input(tmp_path):
    p = tmp_path / "bars.jsonl"
    p.write_text(json.dumps(_bar_payload("2025-06-02T12:01:00+00:00")) + "\n" + json.dumps(_bar_payload()) + "\n")
    with pytest.raises(ValueError, match="globally chronological"):
        load_authoritative_bars_jsonl(p)


def test_contract_master_loader_checks_declared_hash(tmp_path):
    rows = [{
        "ticker": "GCQ5", "product_code": "GC", "first_trade_date": "2023-09-29",
        "last_trade_date": "2025-08-27", "settlement_date": "2025-08-27",
    }]
    master = build_gc_contract_master(rows)
    p = tmp_path / "master.json"
    p.write_text(json.dumps({"master_hash": master.master_hash, "specs": rows}))
    assert load_contract_master_json(p).master_hash == master.master_hash
    p.write_text(json.dumps({"master_hash": "bad", "specs": rows}))
    with pytest.raises(ValueError, match="declared contract master hash mismatch"):
        load_contract_master_json(p)


def test_lineage_loader_recomputes_hash(tmp_path):
    b = HistoricalBar(
        instrument="GC", contract="GCQ5", event_time=datetime(2025, 6, 2, 12, tzinfo=timezone.utc),
        open=3300.0, high=3301.0, low=3299.0, close=3300.5, volume=10.0,
        quality_state=QualityState.VERIFIED, source_id="massive:real", roll_method=RollMethod.RAW_CONTRACT,
    )
    dh = build_gc_dataset_manifest((b,)).dataset_hash
    provisional = AcquisitionLineageManifest(
        5, 0, (RollDecisionLineage("2025-06-02", "2025-05-30", "GCQ5", (("GCQ5", 100.0),)),),
        (("GCQ5", "2025-06-02", "2025-06-02"),), dh, "PENDING", 365, "master",
    )
    h = compute_acquisition_lineage_hash(provisional)
    payload = {
        "roll_buffer_days": 5, "roll_buffer_bars": 0, "max_settlement_days_forward": 365,
        "contract_master_hash": "master", "dataset_hash": dh, "lineage_hash": h,
        "decisions": [{"as_of": "2025-06-02", "liquidity_session_date": "2025-05-30", "selected_contract": "GCQ5", "volume_by_contract": [["GCQ5", 100.0]]}],
        "fetch_windows": [["GCQ5", "2025-06-02", "2025-06-02"]],
    }
    p = tmp_path / "lineage.json"
    p.write_text(json.dumps(payload))
    assert load_acquisition_lineage_json(p).lineage_hash == h
    payload["decisions"][0]["volume_by_contract"][0][1] = 99.0
    p.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="lineage hash mismatch"):
        load_acquisition_lineage_json(p)


def test_macro_loader_checks_declared_hash(tmp_path):
    event = MacroEvent(
        datetime(2025, 6, 2, 12, 30, tzinfo=timezone.utc),
        datetime(2025, 1, 1, tzinfo=timezone.utc), "CPI",
    )
    snapshot = build_macro_calendar_snapshot(
        coverage_start=datetime(2025, 6, 1).date(), coverage_end=datetime(2025, 6, 3).date(),
        source_id="official:calendar", events=(event,),
    )
    payload = {
        "coverage_start": "2025-06-01", "coverage_end": "2025-06-03", "source_id": "official:calendar",
        "calendar_hash": snapshot.calendar_hash,
        "events": [{"event_time": event.event_time.isoformat(), "known_at": event.known_at.isoformat(), "category": "CPI"}],
    }
    p = tmp_path / "macro.json"
    p.write_text(json.dumps(payload))
    assert load_macro_calendar_json(p).calendar_hash == snapshot.calendar_hash
    payload["calendar_hash"] = "bad"
    p.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="declared macro calendar hash mismatch"):
        load_macro_calendar_json(p)
