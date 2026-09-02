"""Clock-health primitives for fail-closed production execution."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class ClockLimits:
    max_abs_offset_ms: float = 100.0
    max_sample_age_ms: float = 2_000.0
    max_jitter_ms: float = 25.0

    def __post_init__(self) -> None:
        if min(self.max_abs_offset_ms, self.max_sample_age_ms, self.max_jitter_ms) <= 0:
            raise ValueError("clock limits must be positive")


@dataclass(frozen=True)
class ClockSample:
    offset_ms: float
    age_ms: float
    jitter_ms: float
    source_count: int


@dataclass(frozen=True)
class ClockDecision:
    healthy: bool
    reason: str


def evaluate_clock(sample: ClockSample, limits: ClockLimits = ClockLimits()) -> ClockDecision:
    values = (sample.offset_ms, sample.age_ms, sample.jitter_ms)
    if not all(isfinite(v) for v in values):
        return ClockDecision(False, "INVALID_CLOCK_METRIC")
    if sample.age_ms < 0 or sample.jitter_ms < 0 or sample.source_count < 1:
        return ClockDecision(False, "INVALID_CLOCK_SAMPLE")
    if sample.source_count < 2:
        return ClockDecision(False, "INSUFFICIENT_CLOCK_SOURCES")
    if abs(sample.offset_ms) > limits.max_abs_offset_ms:
        return ClockDecision(False, "CLOCK_OFFSET_VETO")
    if sample.age_ms > limits.max_sample_age_ms:
        return ClockDecision(False, "CLOCK_SAMPLE_STALE")
    if sample.jitter_ms > limits.max_jitter_ms:
        return ClockDecision(False, "CLOCK_JITTER_VETO")
    return ClockDecision(True, "CLOCK_HEALTHY")
