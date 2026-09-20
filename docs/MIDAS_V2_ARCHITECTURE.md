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
