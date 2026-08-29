#!/usr/bin/env python3
"""Run the locked EXP-0001 formal test from one hash-bound evidence bundle."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from gold_cio_v9.data.dataset_manifest import build_gc_dataset_manifest
from gold_cio_v9.validation.evidence_bundle import load_evidence_bundle
from gold_cio_v9.validation.exp0001_full_test import run_formal_exp0001_test
from gold_cio_v9.validation.ledger import EvidenceLedger
from gold_cio_v9.validation.trials import TrialsRegistry


def main() -> int:
    p = argparse.ArgumentParser(description="Run locked Gold CIO EXP-0001 evidence test")
    p.add_argument("--bundle", required=True)
    p.add_argument("--git-commit", required=True)
    p.add_argument("--trials", required=True)
    p.add_argument("--ledger", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    bundle = load_evidence_bundle(args.bundle)
    manifest = build_gc_dataset_manifest(bundle.bars)
    outcome = run_formal_exp0001_test(
        bars=bundle.bars,
        dataset_manifest=manifest,
        acquisition_lineage=bundle.acquisition_lineage,
        macro_calendar=bundle.macro_calendar,
        base_costs=bundle.base_costs,
        trial_registry=TrialsRegistry(args.trials),
        evidence_ledger=EvidenceLedger(args.ledger),
        git_commit=args.git_commit,
    )
    result = {
        "bundle_hash": bundle.bundle_hash,
        "dataset_hash": bundle.dataset_hash,
        "macro_calendar_hash": bundle.macro_calendar.calendar_hash,
        "macro_source_id": bundle.macro_calendar.source_id,
        "verdict": outcome.verdict,
        "failed_gates": list(outcome.failed_gates),
        "trial_id": outcome.trial.trial_id,
        "config_hash": outcome.trial.config_hash,
        "data_snapshot_hash": outcome.data_snapshot_hash,
        "candidate_snapshot_hash": outcome.candidate_snapshot_hash,
        "result_hash": outcome.result_hash,
        "metrics": asdict(outcome.validation.metrics),
        "diagnostics": asdict(outcome.validation.diagnostics),
    }
    Path(args.output).write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"verdict": outcome.verdict, "trial_id": outcome.trial.trial_id, "result_hash": outcome.result_hash}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
