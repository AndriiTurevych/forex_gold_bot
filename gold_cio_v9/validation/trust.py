"""Tester-trust primitives for Gold CIO v9.1.

These utilities exist to validate the tester itself before any alpha result is trusted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Iterable, Mapping, Any


class PITViolation(ValueError):
    pass


@dataclass(frozen=True)
class PITObservation:
    event_time: datetime
    available_time: datetime
    source_max_event_time: datetime


def assert_point_in_time(obs: Iterable[PITObservation]) -> None:
    """Fail if a feature depends on information that was not available at decision time."""
    for i, row in enumerate(obs):
        if row.available_time < row.event_time:
            raise PITViolation(f"PIT_AVAILABLE_BEFORE_EVENT:{i}")
        if row.source_max_event_time > row.available_time:
            raise PITViolation(f"PIT_FUTURE_SOURCE_DEPENDENCY:{i}")


def purge_training_indices(
    train_intervals: list[tuple[datetime, datetime]],
    test_intervals: list[tuple[datetime, datetime]],
) -> list[int]:
    """Return training rows whose label intervals do not overlap any test interval."""
    keep: list[int] = []
    for i, (a0, a1) in enumerate(train_intervals):
        overlaps = any(a0 <= b1 and b0 <= a1 for b0, b1 in test_intervals)
        if not overlaps:
            keep.append(i)
    return keep


def canonical_hash(payload: Any) -> str:
    """Stable SHA256 over canonical JSON for deterministic replay comparisons."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def reject_runtime_overrides(config: Mapping[str, Any], overrides: Mapping[str, Any] | None) -> None:
    if not overrides:
        return
    if config.get("runtime_overrides_allowed", False):
        return
    changed = {k: v for k, v in overrides.items() if config.get(k) != v}
    if changed:
        raise ValueError("RUNTIME_CONFIG_OVERRIDE_FORBIDDEN")
