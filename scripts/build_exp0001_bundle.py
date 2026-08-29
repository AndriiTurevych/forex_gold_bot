#!/usr/bin/env python3
"""Build a hash-bound EXP-0001 bundle from verified external evidence files."""
from __future__ import annotations

import argparse
import json

from gold_cio_v9.experiments.exp0001_locked import LOCKED_BASE_COSTS
from gold_cio_v9.validation.evidence_bundle import build_evidence_bundle, dump_evidence_bundle
from gold_cio_v9.validation.evidence_inputs import (
    load_acquisition_lineage_json,
    load_authoritative_bars_jsonl,
    load_contract_master_json,
    load_macro_calendar_json,
)
from gold_cio_v9.validation.test_readiness import assess_exp0001_test_readiness


def main() -> int:
    p = argparse.ArgumentParser(description="Build locked Gold CIO EXP-0001 evidence bundle")
    p.add_argument("--bars", required=True, help="Authoritative raw GC bars JSONL")
    p.add_argument("--lineage", required=True, help="Acquisition lineage JSON")
    p.add_argument("--contract-master", required=True, help="Immutable GC contract master JSON")
    p.add_argument("--macro-calendar", required=True, help="PIT macro calendar JSON")
    p.add_argument("--output", required=True, help="Output evidence bundle JSON")
    args = p.parse_args()

    bars = load_authoritative_bars_jsonl(args.bars)
    lineage = load_acquisition_lineage_json(args.lineage)
    master = load_contract_master_json(args.contract_master)
    macro = load_macro_calendar_json(args.macro_calendar)
    bundle = build_evidence_bundle(
        bars=bars,
        acquisition_lineage=lineage,
        contract_master=master,
        macro_calendar=macro,
        base_costs=LOCKED_BASE_COSTS,
    )
    dump_evidence_bundle(bundle, args.output)
    readiness = assess_exp0001_test_readiness(bundle)
    print(json.dumps({
        "bundle_hash": bundle.bundle_hash,
        "dataset_hash": bundle.dataset_hash,
        "contract_master_hash": master.master_hash,
        "lineage_hash": lineage.lineage_hash,
        "macro_calendar_hash": macro.calendar_hash,
        "bars": len(bars),
        "contracts": list(readiness.contracts),
        "coverage": [readiness.coverage_start, readiness.coverage_end],
        "ready": readiness.ready,
        "failed_checks": [c.name for c in readiness.failed_checks],
    }, sort_keys=True))
    return 0 if readiness.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
