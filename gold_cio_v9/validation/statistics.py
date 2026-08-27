"""Statistical validation primitives for Gold CIO evidence runs.

These functions are deterministic and dependency-light so they can be used in CI.
They are not a substitute for full research notebooks; they provide production
checks used by the evidence orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import erf, isfinite, log, sqrt
from statistics import mean, pstdev
from typing import Sequence


@dataclass(frozen=True)
class SharpeEvidence:
    sharpe: float
    deflated_z: float
    p_value: float
    significant: bool


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def sample_sharpe(values: Sequence[float]) -> float:
    xs = [float(x) for x in values if isfinite(float(x))]
    if len(xs) < 2:
        raise ValueError("at least two finite observations required")
    sd = pstdev(xs)
    if sd == 0:
        return float("inf") if mean(xs) > 0 else 0.0
    return mean(xs) / sd


def deflated_sharpe_test(
    values: Sequence[float],
    *,
    trials: int,
    alpha: float = 0.05,
) -> SharpeEvidence:
    """Conservative multiple-trial Sharpe significance screen.

    We use a Bonferroni-adjusted one-sided normal threshold around the observed
    per-trade Sharpe. This is deliberately conservative and production-safe.
    Research may additionally compute the full Bailey/Lopez-de-Prado DSR.
    """
    if trials < 1:
        raise ValueError("trials must be >= 1")
    xs = [float(x) for x in values if isfinite(float(x))]
    if len(xs) < 3:
        raise ValueError("at least three finite observations required")
    sr = sample_sharpe(xs)
    if not isfinite(sr):
        return SharpeEvidence(sr, float("inf"), 0.0, True)
    z = sr * sqrt(len(xs))
    raw_p = 1.0 - _normal_cdf(z)
    adjusted_p = min(1.0, raw_p * trials)
    return SharpeEvidence(sr, z, adjusted_p, adjusted_p < alpha)


def pbo_from_rank_paths(is_rank: Sequence[int], oos_rank: Sequence[int]) -> float:
    """Estimate PBO from paired in-sample/OOS ranks.

    Rank 1 means best. PBO is the fraction of paths where the IS winner lands in
    the bottom half OOS. Caller is responsible for CPCV path construction.
    """
    if len(is_rank) != len(oos_rank) or not is_rank:
        raise ValueError("rank vectors must be non-empty and same length")
    n = len(is_rank)
    bottom_cut = max(1, n // 2)
    failures = sum(1 for i, o in zip(is_rank, oos_rank) if i == 1 and o > bottom_cut)
    winners = sum(1 for i in is_rank if i == 1)
    if winners == 0:
        raise ValueError("no in-sample winner observations")
    return failures / winners
