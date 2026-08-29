#!/usr/bin/env python3
"""Materialize locked EXP-0001 GC evidence directly from Massive REST data.

Requires MASSIVE_API_KEY in the environment. This command performs data acquisition,
causal contract selection and deterministic file materialization only; it never
imports or executes the strategy pipeline.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import time
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from gold_cio_v9.data.massive_evidence_acquisition import (
    acquire_exp0001_massive_evidence,
    dump_acquisition_lineage_json,
    dump_authoritative_bars_jsonl,
)
from gold_cio_v9.validation.evidence_inputs import load_contract_master_json

DEFAULT_BASE_URL = "https://api.massive.com"
DEFAULT_MASTER = "gold_cio_v9/data/gc_contract_master_2025_2026.json"


class MassiveHttpTransport:
    def __init__(self, api_key: str, *, base_url: str = DEFAULT_BASE_URL, max_retries: int = 6):
        if not api_key.strip():
            raise ValueError("MASSIVE_API_KEY is required")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/") + "/"
        self.max_retries = max_retries
        host = urlparse(self.base_url).netloc.lower()
        if not host:
            raise ValueError("Massive base URL must be absolute")
        self.allowed_host = host

    def _url(self, target: str, params: Mapping[str, object]) -> str:
        raw = target if target.startswith("http://") or target.startswith("https://") else urljoin(self.base_url, target.lstrip("/"))
        parsed = urlparse(raw)
        if parsed.netloc.lower() != self.allowed_host:
            raise ValueError("Massive pagination attempted to leave configured API host")
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update({str(k): str(v) for k, v in params.items()})
        query["apiKey"] = self.api_key
        return urlunparse(parsed._replace(query=urlencode(query)))

    def __call__(self, target: str, params: Mapping[str, object]):
        url = self._url(target, params)
        for attempt in range(self.max_retries + 1):
            request = Request(url, headers={"Accept": "application/json", "User-Agent": "Gold-CIO-v9-EXP0001/1.0"})
            try:
                with urlopen(request, timeout=60) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Massive API returned non-object JSON")
                return payload
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt >= self.max_retries:
                    raise
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(30.0, 2.0 ** attempt)
                time.sleep(delay)
            except URLError:
                if attempt >= self.max_retries:
                    raise
                time.sleep(min(30.0, 2.0 ** attempt))
        raise RuntimeError("unreachable Massive retry state")


def _dump_master_with_hash(master_path: str, output: Path) -> str:
    master = load_contract_master_json(master_path)
    raw = json.loads(Path(master_path).read_text(encoding="utf-8"))
    specs = raw["specs"] if isinstance(raw, dict) else raw
    output.write_text(json.dumps({"master_hash": master.master_hash, "specs": specs}, sort_keys=True, indent=2), encoding="utf-8")
    return master.master_hash


def main() -> int:
    p = argparse.ArgumentParser(description="Acquire locked EXP-0001 raw GC evidence from Massive")
    p.add_argument("--start", default="2025-04-03")
    p.add_argument("--end", default="2026-08-27")
    p.add_argument("--contract-master", default=DEFAULT_MASTER)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = p.parse_args()

    api_key = os.environ.get("MASSIVE_API_KEY", "")
    transport = MassiveHttpTransport(api_key, base_url=args.base_url)
    master = load_contract_master_json(args.contract_master)
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if end < start:
        raise ValueError("--end precedes --start")

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = acquire_exp0001_massive_evidence(
        transport, master=master, coverage_start=start, coverage_end=end,
    )

    bars_path = out / "bars.jsonl"
    lineage_path = out / "lineage.json"
    master_path = out / "contract_master.json"
    summary_path = out / "acquisition_summary.json"
    dump_authoritative_bars_jsonl(result, bars_path)
    dump_acquisition_lineage_json(result, lineage_path)
    master_hash = _dump_master_with_hash(args.contract_master, master_path)

    summary = {
        "provider": "Massive",
        "coverage_session_start": start.isoformat(),
        "coverage_session_end": end.isoformat(),
        "bars": len(result.dataset.bars),
        "contracts": list(result.dataset.manifest.contracts),
        "dataset_hash": result.dataset.manifest.dataset_hash,
        "contract_master_hash": master_hash,
        "lineage_hash": result.lineage.lineage_hash,
        "roll_buffer_days": result.lineage.roll_buffer_days,
        "roll_buffer_bars": result.lineage.roll_buffer_bars,
        "max_settlement_days_forward": result.lineage.max_settlement_days_forward,
        "fetch_windows": [list(x) for x in result.lineage.fetch_windows],
        "strategy_outcomes_generated": false if False else False,
    }
    summary_path.write_text(json.dumps(summary, sort_keys=True, indent=2), encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
