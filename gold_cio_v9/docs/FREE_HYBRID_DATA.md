# Free hybrid market-data path

Status: **IMPLEMENTED_FEED_PREFLIGHT; NO ORDERS; NOT EXP-0004 ACTIVATION.**

Gold CIO uses each source only for the instrument and purpose it actually
represents:

| Source | Instrument | Purpose | May activate EXP-0004? |
| --- | --- | --- | --- |
| Massive Basic | Raw COMEX GC contract | History and COMEX experiment evidence | Only if its GC bars pass the locked 20-minute gate |
| Local broker MT5 | Broker-specific XAUUSD/Gold CFD | Current bid/ask, spread, broker M1 bars and execution-feasibility research | No |
| CME delayed display | COMEX GC | Human/independent delayed cross-check | No |
| CFTC/Fed/BLS/FRED | Positioning and macro | Slow context/veto evidence | No |

The MT5 collector never calls an order function, exports no account login/name
or server, includes only closed M1 bars, seals the snapshot, and sets
`real_orders_allowed=false`. The validator rejects a changed hash, unexpected
symbol, crossed/abnormal spread, future timestamps, quote age above 10 seconds,
bar age above 20 minutes and malformed/unsorted bars.

## One-time Windows setup

1. Install and open the intended broker's MetaTrader 5 terminal on an always-on
   Windows PC or VPS. Sign in yourself and make the exact gold symbol visible in
   Market Watch. Never put the MT5 password in GitHub or chat.
2. Add that Windows machine as a GitHub self-hosted runner for this repository
   and give it the custom label `gold-cio-mt5`. Run the runner only under a
   dedicated low-privilege Windows account.
3. In GitHub Actions run **MT5 XAUUSD Broker Feed Preflight** and enter the exact
   broker symbol (`XAUUSD`, `GOLD`, or the broker suffix). The workflow is manual
   until the first clean preflight; no unattended schedule is installed yet.

Local verification without a GitHub runner:

```powershell
python -m pip install MetaTrader5 pytest
$env:PYTHONPATH='.'
python -m pytest -q gold_cio_v9/tests/test_mt5_snapshot.py
python scripts/collect_mt5_xauusd.py --symbol XAUUSD --bars 2880 --output mt5_artifacts/snapshot.json
python scripts/preflight_mt5_xauusd.py --snapshot mt5_artifacts/snapshot.json --symbol XAUUSD --output mt5_artifacts/preflight.json --fail-on-not-ready
```

A green broker-feed preflight proves only that the intended broker feed is fresh
and mechanically usable. It is not alpha evidence, a BUY/SELL signal, permission
for live orders, or a substitute for the registered COMEX GC experiment.
