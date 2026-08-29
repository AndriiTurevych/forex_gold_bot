"""Distribution-level latency telemetry for production readiness."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


def _percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("latency sample is empty")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0,1]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = q * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    weight = rank - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


@dataclass(frozen=True)
class LatencyDistribution:
    count: int
    minimum_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    p999_ms: float
    maximum_ms: float


def summarize_latency(values_ms: list[float]) -> LatencyDistribution:
    if not values_ms:
        raise ValueError("latency sample is empty")
    if any((not isfinite(v)) or v < 0 for v in values_ms):
        raise ValueError("latency values must be finite and non-negative")
    return LatencyDistribution(
        count=len(values_ms),
        minimum_ms=min(values_ms),
        p50_ms=_percentile(values_ms, 0.50),
        p95_ms=_percentile(values_ms, 0.95),
        p99_ms=_percentile(values_ms, 0.99),
        p999_ms=_percentile(values_ms, 0.999),
        maximum_ms=max(values_ms),
    )
