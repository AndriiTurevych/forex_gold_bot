# Gold CIO v9

Evidence-first XAUUSD / COMEX Gold research and shadow-trading stack.

## Governing rule

AI may propose. Evidence may promote. Deterministic Risk may veto. Nothing overrides Risk.

## Pipeline

Raw Data -> Point-in-Time Feature Store -> ICT Event Engine -> Candidate Generator -> Label/Cost Engine -> Validation -> Challenger Tournament -> Shadow Trading -> Micro Live.

## Phase 1

First preregistered alpha family: Liquidity Sweep Reversal.

HTF location + external/session liquidity sweep + displacement + MSS + FVG/IFVG retest -> opposing liquidity.

The initial implementation must compare this family against simple non-ICT baselines and must include realistic transaction costs, purged/embargo validation, walk-forward testing, DSR/PBO and an untouched final holdout.

## MIDAS v10 Lean

The locked candidate composes H1/H4 agreement with the causal sequence liquidity
sweep -> displacement/MSS -> FVG/IFVG -> retest on M15. It trades only in the
06:00-20:00 UTC London/New York window, risks at most 0.25% per trade, locks at
0.5% daily loss and permits at most two entries per day.

Run a shadow decision:

```bash
python scripts/run_midas_v10_shadow.py --input gold_cio_v9/config/midas_v10_example.json
```

The evaluator always emits `execution_allowed=false`. Live promotion requires a
separate, passing OOS evidence bundle; a successful smoke test is not alpha.

## Windows VPS: plug-and-play MT5 shadow bridge

Prerequisites: MT5 is open and connected in the current Windows session, the
repository virtual environment exists, `MetaTrader5` is installed, and the
`MIDAS_INGEST_TOKEN` user environment variable is set. Then install or repair
the complete bridge with one command from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_midas_mt5_bridge.ps1
```

The installer performs a real one-shot preflight before replacing the scheduled
task. It then starts one persistent interactive loop at Windows logon, because
the MT5 Python IPC must share the signed-in desktop session with `terminal64`.
Disconnecting Remote Desktop is safe; signing out stops MT5 and the bridge until
the next login. The loop publishes once per minute, records
`mt5_artifacts/bridge.log`, and atomically updates
`mt5_artifacts/health.json`.

Check health at any time:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_midas_mt5_bridge.ps1
```

Both the bridge and its analysis remain shadow-only:
`execution_allowed=false` and `real_orders_allowed=false`.
