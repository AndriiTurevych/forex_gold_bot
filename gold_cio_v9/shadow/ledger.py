"""Append-only hash-chained JSONL ledger for prospective shadow evidence."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path


GENESIS_HASH = "0" * 64


def _hash(seq: int, event_type: str, payload: dict, previous_hash: str) -> str:
    raw = json.dumps({
        "seq": seq, "event_type": event_type, "payload": payload,
        "previous_hash": previous_hash,
    }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha256(raw).hexdigest()


class HashChainLedger:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read_verified(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        previous = GENESIS_HASH
        for expected_seq, row in enumerate(rows, start=1):
            if row.get("seq") != expected_seq or row.get("previous_hash") != previous:
                raise ValueError("SHADOW_LEDGER_CHAIN_BROKEN")
            expected = _hash(expected_seq, row["event_type"], row["payload"], previous)
            if row.get("record_hash") != expected:
                raise ValueError("SHADOW_LEDGER_HASH_MISMATCH")
            previous = expected
        return rows

    def append(self, event_type: str, payload: dict) -> dict:
        if not event_type.strip():
            raise ValueError("event_type is required")
        rows = self.read_verified()
        seq = len(rows) + 1
        previous = rows[-1]["record_hash"] if rows else GENESIS_HASH
        row = {
            "seq": seq, "event_type": event_type, "payload": payload,
            "previous_hash": previous,
            "record_hash": _hash(seq, event_type, payload, previous),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return row
