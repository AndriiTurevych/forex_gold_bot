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
