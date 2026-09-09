from datetime import datetime, timezone
from zipfile import ZipFile
import json

import pytest

from gold_cio_v9.forward_v4_recovery import (
    RecoveryAnchor, build_anchor, read_anchor, restore_exact_archive,
    verify_against_anchor, write_anchor,
)
from gold_cio_v9.forward_v4_validation import policy_hash
from gold_cio_v9.shadow.ledger import HashChainLedger

ENGINE = "a" * 40


def ledger_at(tmp_path, events=1):
    ledger = HashChainLedger(tmp_path / "exp0004_ledger.jsonl")
    ledger.append("GENESIS", {"experiment_id": "EXP-0004", "scope": "PROSPECTIVE_NONBINDING",
                              "engine_commit": ENGINE, "protocol_hash": policy_hash(),
                              "start_time": datetime(2026, 9, 10, tzinfo=timezone.utc).isoformat()})
    for n in range(events - 1):
        ledger.append("HEARTBEAT", {"experiment_id": "EXP-0004", "n": n})
    return ledger


def test_anchor_roundtrip_and_exact_artifact_restore(tmp_path):
    ledger = ledger_at(tmp_path, 2)
    anchor = build_anchor(ledger, artifact_id=101, engine_commit=ENGINE)
    path = tmp_path / "anchor.json"
    write_anchor(path, anchor, exclusive=True)
    assert read_anchor(path) == anchor
    archive = tmp_path / "artifact.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.write(ledger.path, "evidence/exp0004_ledger.jsonl")
    restored = restore_exact_archive(archive, tmp_path / "restored.jsonl", anchor, ENGINE)
    assert restored.read_verified() == ledger.read_verified()


def test_valid_truncation_and_full_rewrite_are_detected(tmp_path):
    ledger = ledger_at(tmp_path, 3)
    anchor = build_anchor(ledger, artifact_id=101, engine_commit=ENGINE)
    rows = ledger.read_verified()
    ledger.path.write_text(json.dumps(rows[0], sort_keys=True, separators=(",", ":")) + "\n")
    assert ledger.read_verified()
    with pytest.raises(ValueError, match="ROLLBACK"):
        verify_against_anchor(ledger, anchor, ENGINE)
    replacement = ledger_at(tmp_path / "replacement", 1)
    ledger.path.write_bytes(replacement.path.read_bytes())
    with pytest.raises(ValueError, match="ROLLBACK"):
        verify_against_anchor(ledger, anchor, ENGINE)


def test_new_anchor_must_extend_exact_previous_prefix(tmp_path):
    ledger = ledger_at(tmp_path, 2)
    first = build_anchor(ledger, artifact_id=101, engine_commit=ENGINE)
    ledger.append("HEARTBEAT", {"experiment_id": "EXP-0004", "n": 10})
    second = build_anchor(ledger, artifact_id=102, engine_commit=ENGINE, previous=first)
    assert second.generation == 2 and second.sequence == 3
    with pytest.raises(ValueError, match="REUSE"):
        build_anchor(ledger, artifact_id=102, engine_commit=ENGINE, previous=second)
    different = ledger_at(tmp_path / "other", 3)
    records = different.read_verified()
    records[1]["payload"]["n"] = 999
    different.path.unlink()
    different.append("GENESIS", records[0]["payload"])
    different.append("HEARTBEAT", records[1]["payload"])
    different.append("HEARTBEAT", records[2]["payload"])
    with pytest.raises(ValueError, match="MISMATCH"):
        build_anchor(different, artifact_id=103, engine_commit=ENGINE, previous=first)


def test_wrong_engine_schema_archive_and_content_fail_closed(tmp_path):
    ledger = ledger_at(tmp_path)
    anchor = build_anchor(ledger, artifact_id=101, engine_commit=ENGINE)
    with pytest.raises(ValueError, match="IMPLEMENTATION"):
        verify_against_anchor(ledger, anchor, "b" * 40)
    bad = dict(anchor.__dict__, extra=True)
    with pytest.raises(ValueError, match="SCHEMA"):
        RecoveryAnchor.parse(bad)
    archive = tmp_path / "bad.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("exp0004_ledger.jsonl", "tampered")
    with pytest.raises(ValueError, match="HASH"):
        restore_exact_archive(archive, tmp_path / "out.jsonl", anchor, ENGINE)
