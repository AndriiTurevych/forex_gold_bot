# MIDAS v2 — AI-Gated Trading Architecture

## Control flow

MT5 broker feed -> deterministic strategy engine -> GPT context gate -> deterministic risk gate -> demo executor -> local position manager -> journal.

The model is not an order generator. It only evaluates a candidate already created by deterministic logic.

## Hard invariants

1. No confirmed deterministic setup -> no AI call.
2. AI can only return ALLOW, REDUCE_RISK, or BLOCK.
3. AI cannot change direction, entry, stop, targets, or directly choose lot size.
4. Any timeout, HTTP error, invalid JSON, invalid schema, or missing API key -> BLOCK.
5. Risk limits are enforced after the AI response.
6. Real orders remain hard-disabled in the v2 gate. Only demo/shadow eligibility can become true.
7. Existing MT5 ingest payload remains unchanged during the first rollout phase.

## Environment

- MIDAS_AI_GATE_ENABLED=1 enables the context gate.
- OPENAI_API_KEY or MIDAS_OPENAI_API_KEY supplies the API key.
- MIDAS_OPENAI_MODEL defaults to gpt-5.6-sol.
- MIDAS_AI_TIMEOUT_SECONDS defaults to 8.
- MIDAS_MAX_RISK_FRACTION defaults to 0.0025.
- MIDAS_MAX_SPREAD_POINTS defaults to 80.
- MIDAS_MIN_RR_TP2 defaults to 1.8.
- MIDAS_MAX_DAILY_LOSS_FRACTION defaults to 0.01.
- MIDAS_MAX_CONSECUTIVE_LOSSES defaults to 3.
- MIDAS_MAX_OPEN_POSITIONS defaults to 1.
- MIDAS_DEMO_EXECUTION_ENABLED defaults to 0 and must be explicitly set to 1.
- MIDAS_MAX_ENTRY_DRIFT_POINTS defaults to 50.
- MIDAS_MT5_DEVIATION_POINTS defaults to 30.
- MIDAS_MT5_MAGIC defaults to 56002026.

## Rollout gates

Phase 1: shadow decisions only. Compare deterministic candidate, AI decision, risk decision, and realized outcome.

Phase 2: demo execution only. The executor hard-checks MT5 ACCOUNT_TRADE_MODE_DEMO, prevents duplicate decisions and duplicate MIDAS positions, places broker-side SL/TP2, and moves SL to breakeven after TP1. Position protection remains local even if the AI/API is unavailable.

Phase 3: real execution is not enabled by this branch. It requires a separate explicit release gate, broker/account preflight, kill switch, and validated drawdown/operational criteria.

## MT5 Expert Advisor backend

The optional EA backend is `mt5/MQL5/Experts/MIDAS/MIDAS_V2_DemoEA.mq5`.

The Python control plane publishes one semicolon-delimited command into MetaTrader `Terminal/Common/Files/MIDAS/midas_command.csv`. MQL5 `FILE_COMMON` is used so the EA and Python bridge share the same sandboxed command channel.

Safety invariants:
- the EA must be explicitly enabled in its inputs;
- only `ACCOUNT_TRADE_MODE_DEMO` is accepted;
- terminal, EA and account-side automated-trading permissions must all be enabled;
- the command must carry `real_orders_allowed=0`;
- expired commands, duplicate decisions, excessive spread, excessive entry drift and invalid geometry are blocked;
- any existing position on the symbol blocks a new MIDAS entry;
- server `ResultRetcode()` is checked after trade operations;
- broker-side SL and TP2 are placed with the entry;
- after TP1 the EA can move SL to breakeven;
- Python demo execution and EA execution cannot be enabled simultaneously.

Environment:
- `MIDAS_EA_COMMAND_ENABLED=1` publishes commands for the EA.
- `MIDAS_EA_COMMAND_TTL_SECONDS` defaults to 90.
- Keep `MIDAS_DEMO_EXECUTION_ENABLED=0` when using the EA backend.

Install and compile on the MT5 Windows host:

`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_midas_v2_ea.ps1`

After compilation, attach `MIDAS_V2_DemoEA` to the broker XAUUSD chart. Leave `InpEnableDemoExecution=false` for shadow validation. Enable it only on a confirmed DEMO account after command flow is verified.

## Final strategy definition

MIDAS v2 default strategy is `CRT_TBS`.

- `H4 -> M15`: the latest fully closed H4 candle defines the CRT range; closed M15 candles can trigger TBS.
- `H1 -> M5`: the latest fully closed H1 candle defines the CRT range; closed M5 candles can trigger TBS.
- A valid TBS trigger must sweep one CRT boundary, close back inside the range, reverse candle body direction, remain within the configured sweep-depth band, and preserve at least the minimum RR to the opposite range boundary.
- One range/side produces one stable `signal_id`; subsequent quote updates cannot create a second execution for the same signal.
- TP1 is the CRT midpoint when geometrically valid; TP2 is the opposite CRT boundary.
- Stop is beyond the sweep extreme plus a volatility buffer.
- H1/H4 trend bias is context for confidence/GPT, not the signal generator.
- ICT is not the default signal generator in MIDAS v2.

## Risk controls

Default risk remains 0.25% of current MT5 equity per trade.

Sizing uses broker `trade_tick_size` and `trade_tick_value_loss` where available. Account state is read locally from MT5 and does not persist login, account name, or broker server.

The deterministic risk gate enforces:
- maximum risk fraction;
- minimum RR to TP2;
- minimum local confidence score;
- maximum spread;
- maximum daily realized loss;
- maximum consecutive MIDAS losses;
- maximum open MIDAS positions;
- optional manual event lock;
- DEMO-account and trade-permission checks whenever an execution backend is enabled.

## High-impact news veto

The EA uses the MetaTrader economic calendar to inspect USD events around execution time. By default it blocks entries from 30 minutes before through 15 minutes after a high-importance USD event. Calendar lookup failure is fail-closed and blocks the entry.

## Cockpit and native template

The EA renders the MIDAS cockpit directly on the chart and draws Entry, SL, TP1 and TP2.

When `InpSaveSafeTemplateOnInit=true` and `InpEnableDemoExecution=false`, the EA calls `ChartSaveTemplate` and creates:

`Profiles\Templates\MIDAS_V2_XAUUSD.tpl`

The saved template is intentionally created only from a safe, non-executing EA instance.

## Forward evidence and Monte Carlo

The EA appends open/close events into:

`Terminal\Common\Files\MIDAS\midas_ea_events.csv`

The bridge converts completed positions into:

`mt5_artifacts\resolved_trades.csv`

Each resolved trade contains realized `r_multiple` based on broker-side cash risk estimated at entry.

Run empirical block-bootstrap Monte Carlo with:

`python scripts/run_midas_monte_carlo.py`

The validation gate requires at least 200 resolved trades, positive mean R, R-based profit factor >= 1.30, positive 5th-percentile 500-trade return, <=5% probability of finishing below start, and <=10% 95th-percentile maximum drawdown at 0.25% risk.

Passing this gate validates DEMO statistics only. It never enables real orders.

## One-command setup

From the repository on the Windows MT5 host:

`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_midas_v2.ps1 -Mode Shadow`

This checks out the MIDAS branch, writes safe environment defaults, securely prompts for the OpenAI API key if missing, compiles/installs the EA, repairs the bridge and runs preflight.

After attaching `MIDAS_V2_DemoEA` to XAUUSD M5, run:

`python scripts/preflight_midas_v2.py --terminal-path "<path to terminal64.exe>"`

For DEMO execution readiness:

`python scripts/preflight_midas_v2.py --terminal-path "<path to terminal64.exe>" --require-demo`

Only after that check is green should `InpEnableDemoExecution=true` be enabled manually in the EA inputs.

## Remaining live boundary

This branch intentionally has no real-money release path. `real_orders_allowed=false` is preserved in analysis, risk decision, command channel, EA event journal and validation outputs. A future live release must be a separate reviewed change after empirical forward evidence.
