"""Causal validation splits for Gold CIO evidence runs.

No strategy logic belongs here. These primitives only define information-safe
train/test partitions using explicit label intervals.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class LabelInterval:
    index: int
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("label interval end must be >= start")


@dataclass(frozen=True)
class Split:
    train: tuple[int, ...]
    test: tuple[int, ...]


def _overlaps(a: LabelInterval, lo: int, hi: int) -> bool:
    return a.start <= hi and a.end >= lo


def purged_kfold(
    intervals: Sequence[LabelInterval],
    k: int,
    embargo: int = 0,
) -> tuple[Split, ...]:
    """Contiguous k-fold with label-overlap purge and post-test embargo.

    `embargo` is expressed in the same integer time coordinate as start/end.
    A training observation is removed if its label interval overlaps the test
    information interval or begins inside the post-test embargo window.
    """
    if k < 2:
        raise ValueError("k must be >= 2")
    if embargo < 0:
        raise ValueError("embargo must be >= 0")
    n = len(intervals)
    if n < k:
        raise ValueError("number of observations must be >= k")

    base, rem = divmod(n, k)
    sizes = [base + (1 if i < rem else 0) for i in range(k)]
    out: list[Split] = []
    cursor = 0
    for size in sizes:
        test_pos = range(cursor, cursor + size)
        test_rows = [intervals[p] for p in test_pos]
        test_lo = min(r.start for r in test_rows)
        test_hi = max(r.end for r in test_rows)
        embargo_hi = test_hi + embargo
        test_ids = tuple(r.index for r in test_rows)
        train_ids = tuple(
            r.index
            for p, r in enumerate(intervals)
            if p < cursor or p >= cursor + size
            if not _overlaps(r, test_lo, test_hi)
            if not (test_hi < r.start <= embargo_hi)
        )
        out.append(Split(train=train_ids, test=test_ids))
        cursor += size
    return tuple(out)


def walk_forward(
    n: int,
    min_train: int,
    test_size: int,
    step: int | None = None,
    rolling_train: int | None = None,
) -> tuple[Split, ...]:
    """Deterministic expanding or rolling walk-forward partitions."""
    if n <= 0 or min_train <= 0 or test_size <= 0:
        raise ValueError("n, min_train and test_size must be positive")
    step = test_size if step is None else step
    if step <= 0:
        raise ValueError("step must be positive")
    if rolling_train is not None and rolling_train < min_train:
        raise ValueError("rolling_train must be >= min_train")

    out: list[Split] = []
    test_start = min_train
    while test_start + test_size <= n:
        train_start = 0 if rolling_train is None else max(0, test_start - rolling_train)
        train = tuple(range(train_start, test_start))
        test = tuple(range(test_start, test_start + test_size))
        out.append(Split(train=train, test=test))
        test_start += step
    return tuple(out)
