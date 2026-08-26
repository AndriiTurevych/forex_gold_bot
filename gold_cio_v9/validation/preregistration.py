"""Technical guardrails for immutable preregistered experiments."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any

import yaml


class PreregistrationPolicyError(RuntimeError):
    """Raised when a preregistered hypothesis or scope has been mutated."""


@dataclass(frozen=True)
class PreregistrationLock:
    experiment_id: str
    path: str
    registered_blob_sha: str
    primary_instrument: str
    secondary_instrument: str | None
    verdict_transfer_allowed: bool


def load_lock(lock_path: str | Path, experiment_id: str) -> PreregistrationLock:
    raw: dict[str, Any] = yaml.safe_load(Path(lock_path).read_text(encoding="utf-8"))
    item = raw["experiments"][experiment_id]
    if item.get("status") != "LOCKED":
        raise PreregistrationPolicyError(f"PREREG_NOT_LOCKED:{experiment_id}")
    return PreregistrationLock(
        experiment_id=experiment_id,
        path=str(item["path"]),
        registered_blob_sha=str(item["registered_blob_sha"]),
        primary_instrument=str(item["primary_instrument"]),
        secondary_instrument=item.get("secondary_instrument"),
        verdict_transfer_allowed=bool(item.get("verdict_transfer_allowed", False)),
    )


def git_blob_sha(path: str | Path) -> str:
    completed = subprocess.run(
        ["git", "hash-object", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def assert_preregistration_immutable(lock: PreregistrationLock) -> None:
    current = git_blob_sha(lock.path)
    if current != lock.registered_blob_sha:
        raise PreregistrationPolicyError(
            f"PREREG_MUTATED:{lock.experiment_id}:{lock.registered_blob_sha}->{current}"
        )


def assert_instrument_scope(lock: PreregistrationLock, instrument: str) -> None:
    """Prevent transferring an EXP verdict to a different traded instrument."""
    if instrument == lock.primary_instrument:
        return
    if instrument == lock.secondary_instrument and not lock.verdict_transfer_allowed:
        raise PreregistrationPolicyError(
            f"VERDICT_TRANSFER_FORBIDDEN:{lock.experiment_id}:{lock.primary_instrument}->{instrument}"
        )
    raise PreregistrationPolicyError(
        f"INSTRUMENT_OUT_OF_SCOPE:{lock.experiment_id}:{instrument}"
    )
