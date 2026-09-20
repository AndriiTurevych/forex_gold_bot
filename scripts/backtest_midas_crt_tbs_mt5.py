#!/usr/bin/env python3
"""Run causal MIDAS CRT+TBS structural replay on broker MT5 M1 history."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from gold_cio_v9.live.backtest_crt_tbs import backtest_crt_tbs, metrics
from gold_cio_v9.live.monte_carlo import monte_carlo_r


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--terminal-path",required=True)
    p.add_argument("--symbol",default="XAUUSD")
    p.add_argument("--days",type=int,default=365)
    p.add_argument("--output-dir",default="mt5_artifacts/backtest_crt_tbs")
    p.add_argument("--min-rr",type=float,default=1.8)
    p.add_argument("--spread-multiplier",type=float,default=1.0)
    p.add_argument("--mt5-timeout-ms",type=int,default=10000)
    args=p.parse_args()
    if args.days<30 or args.days>1825:
        raise ValueError("DAYS_MUST_BE_30_TO_1825")

    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError("MetaTrader5 package is required") from exc

    if not mt5.initialize(path=args.terminal_path,timeout=args.mt5_timeout_ms):
        raise RuntimeError(f"MT5_INITIALIZE_FAILED:{mt5.last_error()}")
    try:
        if not mt5.symbol_select(args.symbol,True):
            raise RuntimeError("MT5_SYMBOL_SELECT_FAILED")
        info=mt5.symbol_info(args.symbol)
        if info is None:
            raise RuntimeError("MT5_SYMBOL_INFO_UNAVAILABLE")
        end=datetime.now(timezone.utc)-timedelta(minutes=1)
        start=end-timedelta(days=args.days)
        rates=mt5.copy_rates_range(args.symbol,mt5.TIMEFRAME_M1,start,end)
        if rates is None or len(rates)==0:
            raise RuntimeError(f"MT5_HISTORY_UNAVAILABLE:{mt5.last_error()}")
        rows=[]
        for rate in rates:
            when=datetime.fromtimestamp(int(rate["time"]),tz=timezone.utc)
            if when+timedelta(minutes=1)>datetime.now(timezone.utc):
                continue
            rows.append({
                "time":when.isoformat(),
                "open":float(rate["open"]),"high":float(rate["high"]),
                "low":float(rate["low"]),"close":float(rate["close"]),
                "spread_points":float(rate["spread"]),
            })
        point=float(getattr(info,"point",0.0) or 0.0)
    finally:
        mt5.shutdown()

    result=backtest_crt_tbs(
        rows,point=point,min_rr_tp2=args.min_rr,spread_multiplier=args.spread_multiplier
    )
    trades=result.pop("trades")
    result["metrics"]=metrics(trades,cost_stress_r=0.0)
    result["metrics_cost_stress_005r"]=metrics(trades,cost_stress_r=0.05)
    result["metrics_cost_stress_010r"]=metrics(trades,cost_stress_r=0.10)

    # Last 20% of resolved trades is reported separately and never used to tune
    # parameters inside this command.
    split=max(1,int(len(trades)*0.80))
    development=trades[:split]
    holdout=trades[split:]
    result["development_metrics"]=metrics(development)
    result["holdout_metrics"]=metrics(holdout)

    if len(trades)>=2:
        result["monte_carlo"]=monte_carlo_r(
            [float(t["r_multiple"]) for t in trades],
            risk_fraction=0.0025,
            paths=20000,
            horizon_trades=500,
            block_size=5,
        )
    else:
        result["monte_carlo"]={"status":"INSUFFICIENT_SAMPLE","sample_size":len(trades)}

    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    (out/"summary.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    fields=[
        "signal_id","model","direction","range_time","trigger_time","signal_time","entry_time",
        "entry","stop","tp1","tp2","entry_spread_points","risk_price","exit_time","exit_price",
        "exit_reason","r_multiple",
    ]
    with (out/"trades.csv").open("w",encoding="utf-8",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields)
        w.writeheader()
        for trade in trades:
            w.writerow({key:trade.get(key) for key in fields})

    print(json.dumps({
        "ok":True,
        "symbol":args.symbol,
        "requested_days":args.days,
        "actual_bars":result["bars"],
        "start_time":result["start_time"],
        "end_time":result["end_time"],
        "resolved_trades":result["resolved_trades"],
        "metrics":result["metrics"],
        "holdout_metrics":result["holdout_metrics"],
        "output_dir":str(out),
        "real_orders_allowed":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
