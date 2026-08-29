#!/usr/bin/env python3
"""Validate a formal EXP-0001 bundle without generating any strategy outcomes."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from gold_cio_v9.validation.evidence_bundle import load_evidence_bundle
from gold_cio_v9.validation.test_readiness import assess_exp0001_test_readiness


def main() -> int:
    p = argparse.ArgumentParser(description="Preflight locked Gold CIO EXP-0001 evidence bundle")
    p.add_argument("--bundle", required=True)
    p.add_argument("--output")
    args = p.parse_args()

    bundle = load_evidence_bundle(args.bundle)
    report = assess_exp0001_test_readiness(bundle)
    payload = asdict(report)
    if args.output:
        Path(args.output).write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "ready": report.ready,
        "bundle_hash": report.bundle_hash,
        "dataset_hash": report.dataset_hash,
        "bars": report.bars,
        "contracts": list(report.contracts),
        "coverage": [report.coverage_start, report.coverage_end],
        "macro_events": report.macro_events,
        "failed_checks": [c.name for c in report.failed_checks],
    }, sort_keys=True))
    return 0 if report.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
