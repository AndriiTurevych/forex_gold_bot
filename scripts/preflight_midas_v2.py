#!/usr/bin/env python3
"""Fail-closed readiness check for MIDAS v2 on the Windows MT5 host."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from gold_cio_v9.live.ai_gate import evaluate_context


def _enabled(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in {"1","true","yes","on"}


def _status_file(path: Path) -> dict:
    if not path.exists():
        return {"exists":False,"fresh":False,"state":None}
    try:
        with path.open("r",encoding="ascii",newline="") as h:
            rows=list(csv.DictReader(h,delimiter=";"))
        if not rows:
            return {"exists":True,"fresh":False,"state":None}
        row=rows[-1]
        # MQL TimeCurrent() is expressed in broker server time. Use the file's
        # filesystem modification time for cross-timezone freshness instead.
        modified=datetime.fromtimestamp(path.stat().st_mtime,tz=timezone.utc)
        age=(datetime.now(timezone.utc)-modified).total_seconds()
        return {"exists":True,"fresh":0<=age<=180,"state":row.get("state"),"age_seconds":round(age,1)}
    except Exception as exc:
        return {"exists":True,"fresh":False,"state":None,"error":type(exc).__name__}


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--terminal-path",required=True)
    p.add_argument("--symbol",default="XAUUSD")
    p.add_argument("--require-demo",action="store_true")
    p.add_argument("--probe-openai",action="store_true")
    p.add_argument("--structural-gate",default="mt5_artifacts/backtest_crt_tbs/validation_gate.json")
    p.add_argument("--mt5-timeout-ms",type=int,default=10000)
    args=p.parse_args()

    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError("MetaTrader5 package is required") from exc

    terminal_path=Path(args.terminal_path)
    checks={}
    initialized=mt5.initialize(path=str(terminal_path),timeout=args.mt5_timeout_ms)
    checks["mt5_initialize"]=bool(initialized)
    if not initialized:
        print(json.dumps({"ready_for_shadow":False,"ready_for_demo_ea":False,"checks":checks,"error":str(mt5.last_error())},sort_keys=True))
        return 1

    try:
        terminal=mt5.terminal_info()
        account=mt5.account_info()
        info=mt5.symbol_info(args.symbol)
        tick=mt5.symbol_info_tick(args.symbol)

        checks["terminal_connected"]=bool(terminal and getattr(terminal,"connected",False))
        checks["account_available"]=account is not None
        checks["symbol_available"]=info is not None and tick is not None
        checks["tick_economics"]=bool(
            info and float(getattr(info,"trade_tick_size",0) or 0)>0
            and float(getattr(info,"trade_tick_value_loss",getattr(info,"trade_tick_value",0)) or 0)>0
        )

        demo_mode=int(getattr(mt5,"ACCOUNT_TRADE_MODE_DEMO",0))
        trade_mode=int(getattr(account,"trade_mode",-1)) if account else -1
        checks["demo_account"]=trade_mode==demo_mode
        checks["account_trade_allowed"]=bool(account and getattr(account,"trade_allowed",False))
        checks["account_expert_allowed"]=bool(account and getattr(account,"trade_expert",False))
        checks["terminal_trade_allowed"]=bool(terminal and getattr(terminal,"trade_allowed",False))

        data_path=Path(str(getattr(terminal,"data_path","") or "")) if terminal else Path()
        common=Path(str(getattr(terminal,"commondata_path","") or "")) if terminal else Path()
        ex5=data_path/"MQL5"/"Experts"/"MIDAS"/"MIDAS_V2_DemoEA.ex5"
        template=data_path/"Profiles"/"Templates"/"MIDAS_V2_XAUUSD.tpl"
        status=common/"Files"/"MIDAS"/"midas_ea_status.csv"
        command=common/"Files"/"MIDAS"/"midas_command.csv"

        checks["ea_compiled"]=ex5.exists()
        checks["safe_template_exists"]=template.exists()
        checks["ea_command_file_exists"]=command.exists()
        checks["ea_status"]=_status_file(status)

        checks["ingest_token"]=bool(os.environ.get("MIDAS_INGEST_TOKEN","").strip() or os.environ.get("MIDAS_INGEST_TOKEN_USER","").strip())
        checks["openai_key"]=bool(os.environ.get("OPENAI_API_KEY","").strip() or os.environ.get("MIDAS_OPENAI_API_KEY","").strip())
        checks["ai_gate_enabled"]=_enabled("MIDAS_AI_GATE_ENABLED")
        checks["ea_command_enabled"]=_enabled("MIDAS_EA_COMMAND_ENABLED")
        checks["python_demo_enabled"]=_enabled("MIDAS_DEMO_EXECUTION_ENABLED")
        checks["execution_backend_conflict"]=checks["ea_command_enabled"] and checks["python_demo_enabled"]

        checks["openai_probe"]=None
        checks["openai_probe_reason"]=None
        if args.probe_openai:
            synthetic_snapshot={
                "instrument":{"symbol":args.symbol,"point":float(getattr(info,"point",0.01) or 0.01)},
                "quote":{"event_time":datetime.now(timezone.utc).isoformat(),"bid":4300.00,"ask":4300.20},
            }
            synthetic_analysis={
                "symbol":args.symbol,
                "decision_time":datetime.now(timezone.utc).isoformat(),
                "state":"CONFIRMED","action":"BUY","reason":"PREFLIGHT_SYNTHETIC_CANDIDATE",
                "h1_bias":"LONG","h4_bias":"LONG",
                "entry":4300.20,"stop":4298.20,"tp1":4302.20,"tp2":4304.20,
                "risk_fraction":0.0025,"confidence_score":80,
                "support_zones":[],"resistance_zones":[],
                "crt_tbs":{"model":"PREFLIGHT","direction":"LONG"},
            }
            probe=evaluate_context(synthetic_snapshot,synthetic_analysis,enabled=True)
            checks["openai_probe"]=probe.get("status")=="OK" and probe.get("decision") in {"ALLOW","REDUCE_RISK","BLOCK"}
            checks["openai_probe_reason"]=probe.get("reason_code")
        else:
            checks["openai_probe"]=checks["openai_key"]

        gate_path=Path(args.structural_gate)
        structural_gate=None
        if gate_path.exists():
            try:
                structural_gate=json.loads(gate_path.read_text(encoding="utf-8"))
            except Exception:
                structural_gate=None
        checks["structural_gate_exists"]=structural_gate is not None
        checks["structural_backtest_passed"]=bool(structural_gate and structural_gate.get("structural_backtest_passed") is True)

        shadow_required=[
            checks["terminal_connected"],checks["account_available"],checks["symbol_available"],
            checks["tick_economics"],checks["ingest_token"],checks["openai_key"],
            checks["ai_gate_enabled"],checks["openai_probe"],not checks["execution_backend_conflict"],
        ]
        ready_shadow=all(shadow_required)

        demo_required=[
            ready_shadow,checks["demo_account"],checks["account_trade_allowed"],
            checks["account_expert_allowed"],checks["terminal_trade_allowed"],
            checks["ea_compiled"],checks["ea_command_enabled"],
            checks["structural_backtest_passed"],
            bool(checks["ea_status"].get("fresh")),
        ]
        if args.require_demo:
            demo_required.append(checks["demo_account"])
        ready_demo=all(demo_required)

        result={
            "schema":"midas-v2-preflight-v1",
            "ready_for_shadow":ready_shadow,
            "ready_for_demo_ea":ready_demo,
            "checks":checks,
            "real_orders_allowed":False,
        }
        print(json.dumps(result,sort_keys=True))
        return 0 if (ready_demo if args.require_demo else ready_shadow) else 1
    finally:
        mt5.shutdown()


if __name__=="__main__":
    raise SystemExit(main())
