"""Deterministic MIDAS confidence scoring and empirical calibration.

A confidence score is not a probability. A probability is exposed only after at
least 100 resolved, matched shadow outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal


@dataclass(frozen=True)
class ConfidenceFactors:
    trend: float
    location: float
    structure: float
    entry_quality: float
    reward_risk: float
    macro: float
    data_quality: float
    model_agreement: float


@dataclass(frozen=True)
class CalibrationEvidence:
    wins: int = 0
    losses: int = 0

    @property
    def sample_size(self) -> int:
        return self.wins + self.losses


@dataclass(frozen=True)
class ConfidenceResult:
    state: Literal["WAIT", "ARMED", "CONFIRMED", "VETO"]
    confidence_score: int
    calibrated_probability: float | None
    calibration_status: Literal["UNCALIBRATED", "CALIBRATED", "VETO"]
    sample_size: int


_WEIGHTS = {
    "trend": 0.18,
    "location": 0.14,
    "structure": 0.18,
    "entry_quality": 0.14,
    "reward_risk": 0.10,
    "macro": 0.10,
    "data_quality": 0.08,
    "model_agreement": 0.08,
}
_MIN_CALIBRATION_SAMPLE = 100


def score_confidence(
    factors: ConfidenceFactors,
    *,
    mss_confirmed: bool,
    retest_confirmed: bool,
    event_lock: bool,
    evidence: CalibrationEvidence = CalibrationEvidence(),
) -> ConfidenceResult:
    if not all(isinstance(v, bool) for v in (mss_confirmed, retest_confirmed, event_lock)):
        raise ValueError("confirmation flags must be boolean")
    if evidence.wins < 0 or evidence.losses < 0:
        raise ValueError("calibration counts cannot be negative")

    values = {name: getattr(factors, name) for name in _WEIGHTS}
    if not all(isfinite(value) and 0.0 <= value <= 1.0 for value in values.values()):
        raise ValueError("confidence factors must be finite and in [0, 1]")

    if event_lock:
        return ConfidenceResult("VETO", 0, None, "VETO", evidence.sample_size)

    score = round(100 * sum(values[name] * weight for name, weight in _WEIGHTS.items()))
    if not mss_confirmed:
        state = "ARMED" if score >= 50 else "WAIT"
        score = min(score, 59)
    elif not retest_confirmed:
        state = "ARMED"
        score = min(score, 69)
    else:
        state = "CONFIRMED"

    probability = None
    status = "UNCALIBRATED"
    if evidence.sample_size >= _MIN_CALIBRATION_SAMPLE:
        probability = (evidence.wins + 1) / (evidence.sample_size + 2)
        status = "CALIBRATED"

    return ConfidenceResult(state, score, probability, status, evidence.sample_size)
