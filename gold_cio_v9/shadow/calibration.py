"""Append-only shadow forecast/outcome records and calibration metrics."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from math import isfinite
from typing import Iterable

from gold_cio_v9.shadow.ledger import HashChainLedger
from gold_cio_v9.strategies.confidence import ConfidenceResult


@dataclass(frozen=True)
class CalibrationSummary:
    resolved: int
    wins: int
    losses: int
    win_rate: float | None
    expectancy_r: float | None
    brier_score: float | None


def record_forecast(
    ledger: HashChainLedger,
    *,
    signal_id: str,
    issued_at: datetime,
    action: str,
    confidence: ConfidenceResult,
) -> dict:
    if not signal_id.strip() or action not in {"BUY", "SELL", "ABSTAIN"}:
        raise ValueError("invalid forecast identity or action")
    return ledger.append("MIDAS_FORECAST", {
        "signal_id": signal_id,
        "issued_at": issued_at.isoformat(),
        "action": action,
        **asdict(confidence),
    })


def record_outcome(
    ledger: HashChainLedger,
    *,
    signal_id: str,
    realized_r: float,
    predicted_probability: float | None,
) -> dict:
    if not signal_id.strip() or not isfinite(realized_r):
        raise ValueError("invalid outcome")
    if predicted_probability is not None and (
        not isfinite(predicted_probability) or not 0.0 <= predicted_probability <= 1.0
    ):
        raise ValueError("predicted_probability must be in [0, 1]")
    return ledger.append("MIDAS_OUTCOME", {
        "signal_id": signal_id,
        "realized_r": realized_r,
        "predicted_probability": predicted_probability,
    })


def summarize_outcomes(rows: Iterable[dict]) -> CalibrationSummary:
    outcomes = [row["payload"] for row in rows if row.get("event_type") == "MIDAS_OUTCOME"]
    if not outcomes:
        return CalibrationSummary(0, 0, 0, None, None, None)

    realized = [float(row["realized_r"]) for row in outcomes]
    if not all(isfinite(value) for value in realized):
        raise ValueError("non-finite realized_r")
    wins = sum(value > 0 for value in realized)
    losses = len(realized) - wins
    probabilities = [
        (float(row["predicted_probability"]), 1.0 if value > 0 else 0.0)
        for row, value in zip(outcomes, realized)
        if row.get("predicted_probability") is not None
    ]
    brier = None
    if probabilities:
        if not all(isfinite(p) and 0.0 <= p <= 1.0 for p, _ in probabilities):
            raise ValueError("invalid predicted probability")
        brier = sum((p - outcome) ** 2 for p, outcome in probabilities) / len(probabilities)

    return CalibrationSummary(
        resolved=len(realized),
        wins=wins,
        losses=losses,
        win_rate=wins / len(realized),
        expectancy_r=sum(realized) / len(realized),
        brier_score=brier,
    )
