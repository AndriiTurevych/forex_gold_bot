#!/usr/bin/env python3
"""Run empirical MIDAS Monte Carlo from resolved demo trades."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from gold_cio_v9.live.monte_carlo import monte_carlo_r, validation_gate


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--trades",default="mt5_artifacts/resolved_trades.csv")
    p.add_argument("--output",default="mt5_artifacts/monte_carlo.json")
    p.add_argument("--gate-output",default="mt5_artifacts/validation_gate.json")
    p.add_argument("--paths",type=int,default=20000)
    p.add_argument("--horizon-trades",type=int,default=500)
    p.add_argument("--block-size",type=int,default=5)
    p.add_argument("--risk-fraction",type=float,default=0.0025)
    args=p.parse_args()

    path=Path(args.trades)
    if not path.exists():
        raise RuntimeError(f"RESOLVED_TRADES_NOT_FOUND:{path}")
    with path.open("r",encoding="utf-8",newline="") as h:
        rows=list(csv.DictReader(h))
    r_values=[float(row["r_multiple"]) for row in rows]
    if len(r_values)<2:
        result={
            "schema":"midas-empirical-monte-carlo-v1",
            "status":"INSUFFICIENT_SAMPLE",
            "sample_size":len(r_values),
            "real_orders_allowed":False,
        }
        gate={
            "schema":"midas-demo-validation-gate-v1",
            "demo_validated":False,
            "sample_size":len(r_values),
            "reasons":["MINIMUM_SAMPLE_NOT_REACHED"],
            "live_release_allowed":False,
            "real_orders_allowed":False,
        }
    else:
        result=monte_carlo_r(
            r_values,
            risk_fraction=args.risk_fraction,
            paths=args.paths,
            horizon_trades=args.horizon_trades,
            block_size=args.block_size,
        )
        gate=validation_gate(result)

    Path(args.output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    Path(args.gate_output).write_text(json.dumps(gate,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"monte_carlo":result,"gate":gate},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
