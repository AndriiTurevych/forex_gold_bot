"""Append-only Evidence Ledger for Gold CIO validation verdicts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


VALID_VERDICTS = {"ACCEPT", "REJECT", "INSUFFICIENT_DATA"}


@dataclass(frozen=True)
class EvidenceRecord:
    recorded_at: str
    experiment_id: str
    trial_id: str
    git_commit: str
    data_snapshot_hash: str
    candidate_snapshot_hash: str
    result_hash: str
    config_hash: str
    verdict: str
    metrics: dict[str, Any]
    failed_gates: tuple[str, ...]


class EvidenceLedger:
    """JSONL append-only ledger. Existing records are never edited in-place."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        *,
        experiment_id: str,
        trial_id: str,
        git_commit: str,
        data_snapshot_hash: str,
        candidate_snapshot_hash: str,
        result_hash: str,
        config_hash: str,
        verdict: str,
        metrics: dict[str, Any],
        failed_gates: tuple[str, ...],
    ) -> EvidenceRecord:
        if verdict not in VALID_VERDICTS:
            allowed = ", ".join(sorted(VALID_VERDICTS))
            raise ValueError(f"verdict must be one of: {allowed}")
        record = EvidenceRecord(
            recorded_at=datetime.now(timezone.utc).isoformat(),
            experiment_id=experiment_id,
            trial_id=trial_id,
            git_commit=git_commit,
            data_snapshot_hash=data_snapshot_hash,
            candidate_snapshot_hash=candidate_snapshot_hash,
            result_hash=result_hash,
            config_hash=config_hash,
            verdict=verdict,
            metrics=metrics,
            failed_gates=tuple(failed_gates),
        )
        payload = asdict(record)
        payload["record_hash"] = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
            f.flush()
        return record

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
