"""Deterministic low-latency execution primitives for Gold CIO v9.1."""

from .latency import LatencyBudget, LatencyTrace, StageTiming
from .fast_path import FastPathContext, FastPathDecision, FastPathInput, FastPathVerdict, evaluate_fast_path

__all__ = [
    "LatencyBudget",
    "LatencyTrace",
    "StageTiming",
    "FastPathContext",
    "FastPathDecision",
    "FastPathInput",
    "FastPathVerdict",
    "evaluate_fast_path",
]
