"""Append-only trials registry used for DSR/PBO accounting."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TrialRecord:
    trial_id: str
    created_at: str
    experiment_id: str
    config_hash: str
    data_snapshot_hash: str
    git_commit: str


def make_config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


class TrialsRegistry:
    """Simple JSONL append-only registry.

    A trial must be registered before the caller exposes any result.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def register(self, *, experiment_id: str, config: dict[str, Any], data_snapshot_hash: str, git_commit: str) -> TrialRecord:
        now = datetime.now(timezone.utc).isoformat()
        cfg_hash = make_config_hash(config)
        trial_id = hashlib.sha256(f"{experiment_id}|{now}|{cfg_hash}|{data_snapshot_hash}|{git_commit}".encode()).hexdigest()[:20]
        record = TrialRecord(trial_id, now, experiment_id, cfg_hash, data_snapshot_hash, git_commit)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), sort_keys=True) + "\n")
            f.flush()
        return record

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
