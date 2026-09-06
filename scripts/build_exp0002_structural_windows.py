#!/usr/bin/env python3
"""Build outcome-free EXP-0002 structural candidate windows from sealed 1m bars."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

from gold_cio_v9.data.governance import HistoricalBar, QualityState, RollMethod
from gold_cio_v9.experiments.exp0001_inputs import build_exp0001_causal_inputs
from gold_cio_v9.experiments.exp0001_locked import ATR_PERIOD, SWING_LEFT_BARS, SWING_RIGHT_BARS
from gold_cio_v9.experiments.exp0001_pipeline import PipelineConfig, _materialize_context_points
from gold_cio_v9.experiments.exp0001_replay import build_replay_candidates
from gold_cio_v9.experiments.exp0001_sequence import assemble_replay_setups
from gold_cio_v9.experiments.exp0001_stream import build_event_stream


def load_bars(path: Path) -> tuple[HistoricalBar, ...]:
    bars = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        bars.append(HistoricalBar(
            instrument=row["instrument"], contract=row["contract"],
            event_time=datetime.fromisoformat(row["event_time"]),
            open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
            close=float(row["close"]), volume=None if row["volume"] is None else float(row["volume"]),
            quality_state=QualityState(row["quality_state"]), source_id=row["source_id"],
            roll_method=RollMethod(row["roll_method"]), is_roll_window=bool(row["is_roll_window"]),
        ))
    if not bars:
        raise ValueError("bars are required")
    return tuple(bars)


def _contract_windows(bars: tuple[HistoricalBar, ...]) -> list[dict[str, object]]:
    config = PipelineConfig(ATR_PERIOD, SWING_LEFT_BARS, SWING_RIGHT_BARS, 60)
    inputs = build_exp0001_causal_inputs(
        bars, atr_period=config.atr_period,
        swing_left_bars=config.swing_left_bars, swing_right_bars=config.swing_right_bars,
    )
    context = _materialize_context_points(
        bars, config=config, prior_trend_by_index=inputs.prior_trend_by_index,
    )
    events = build_event_stream(bars, context)
    setups = assemble_replay_setups(
        bars=bars, events=events, context=context,
        htf_permission=inputs.htf_permission_by_index, horizon_bars=60,
    )
    accepted = build_replay_candidates(list(setups))
    setup_by_id = {setup.setup_id: setup for setup in setups}
    rows: list[dict[str, object]] = []
    for candidate in accepted:
        setup = setup_by_id[candidate.candidate_id]
        end = setup.structure.event_time
        rows.append({
            "candidate_id": candidate.candidate_id.replace("EXP-0001-", "EXP-0002-", 1),
            "contract": bars[candidate.signal_index].contract,
            "direction": candidate.direction,
            "structural_signal_time": bars[candidate.signal_index].event_time.isoformat(),
            "flow_window_start": (end - timedelta(seconds=60)).isoformat(),
            "flow_window_end": end.isoformat(),
        })
    return rows


def build_windows(bars: tuple[HistoricalBar, ...]) -> dict[str, object]:
    # Causal swing/day state must never cross a raw futures roll. Run each
    # contract independently, then combine only the outcome-free window rows.
    grouped: dict[str, list[HistoricalBar]] = defaultdict(list)
    for bar in bars:
        grouped[str(bar.contract)].append(bar)
    rows = []
    for contract in sorted(grouped):
        rows.extend(_contract_windows(tuple(grouped[contract])))
    rows.sort(key=lambda row: (row["structural_signal_time"], row["contract"], row["candidate_id"]))
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema": "gold-cio-exp0002-structural-windows-v1",
        "experiment_id": "EXP-0002",
        "scope": "AVAILABLE_TAIL_ENGINEERING_DRY_RUN_ONLY",
        "complete_preregistered_evidence": False,
        "structural_policy": "EXP-0001-BASELINE-POLICY-V5",
        "candidate_count": len(rows),
        "candidate_windows_hash": sha256(encoded).hexdigest(),
        "candidates": rows,
        "tick_flow_applied": False,
        "strategy_outcomes_generated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build_windows(load_bars(Path(args.bars)))
    Path(args.output).write_text(json.dumps(result, sort_keys=True, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "scope", "candidate_count", "candidate_windows_hash",
        "tick_flow_applied", "strategy_outcomes_generated",
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

