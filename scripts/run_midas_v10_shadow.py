#!/usr/bin/env python3
"""Evaluate one fully specified MIDAS v10 candidate. Shadow output only."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from gold_cio_v9.experiments.exp0001_signal import FVGZone, TimedStructure, TimedSweep
from gold_cio_v9.ict_engine.features import Bar, Sweep
from gold_cio_v9.ict_engine.structure import StructureEvent
from gold_cio_v9.risk.gate import RiskState
from gold_cio_v9.strategies.confidence import CalibrationEvidence, ConfidenceFactors
from gold_cio_v9.strategies.midas_v10_lean import MidasInputs, evaluate_midas


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build(payload: dict) -> MidasInputs:
    r, s, m, z, b = (payload[k] for k in ("risk", "sweep", "structure", "zone", "retest_bar"))
    return MidasInputs(
        decision_time=dt(payload["decision_time"]),
        h1_bias=payload["h1_bias"],
        h4_bias=payload["h4_bias"],
        trades_today=int(payload["trades_today"]),
        equity=float(payload["equity"]),
        point_value=float(payload["point_value"]),
        atr=float(payload["atr"]),
        risk_state=RiskState(**r),
        htf_location_ok=bool(payload["htf_location_ok"]),
        sweep=TimedSweep(dt(s["event_time"]), Sweep(s["side"], float(s["level"]), float(s["depth"]))),
        structure=TimedStructure(
            dt(m["event_time"]),
            StructureEvent(m["kind"], m["direction"], float(m["broken_level"]), float(m["close_price"]), float(m["displacement_atr"])),
        ),
        zone=FVGZone(dt(z["event_time"]), float(z["low"]), float(z["high"]), z["direction"], z.get("kind", "FVG")),
        retest_bar=Bar(b["ts"], float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])),
        confidence_factors=ConfidenceFactors(**payload["confidence"]) if "confidence" in payload else None,
        calibration_evidence=CalibrationEvidence(**payload.get("calibration", {})),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        decision = evaluate_midas(build(payload))
        print(json.dumps(asdict(decision), sort_keys=True))
        return 0
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"action": "ABSTAIN", "execution_allowed": False, "reason": "INVALID_INPUT", "detail": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
