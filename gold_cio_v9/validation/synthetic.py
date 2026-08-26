"""Synthetic fixtures for validating tester behavior before real alpha tests."""
from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class SyntheticCase:
    name: str
    returns_r: tuple[float, ...]


def pure_noise(seed: int = 1729, n: int = 400) -> SyntheticCase:
    rng = random.Random(seed)
    vals = tuple(0.25 if rng.random() < 0.5 else -0.25 for _ in range(n))
    return SyntheticCase("pure_noise", vals)


def strong_edge(seed: int = 1729, n: int = 400) -> SyntheticCase:
    """Deterministic positive edge designed to survive conservative synthetic costs."""
    rng = random.Random(seed)
    vals = []
    for i in range(n):
        # 75% +1.2R / 25% -1R; deterministic from fixed seed.
        vals.append(1.2 if rng.random() < 0.75 else -1.0)
    return SyntheticCase("strong_edge", tuple(vals))


def expectancy(values: tuple[float, ...], cost_r: float = 0.0) -> float:
    if not values:
        return 0.0
    return sum(v - cost_r for v in values) / len(values)


def profit_factor(values: tuple[float, ...], cost_r: float = 0.0) -> float:
    net = [v - cost_r for v in values]
    gains = sum(v for v in net if v > 0)
    losses = -sum(v for v in net if v < 0)
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses
