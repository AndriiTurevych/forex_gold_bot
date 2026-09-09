# EXP-0005 — XAUUSD/GC intraday scalp research design

Status: **DESIGN_ONLY; NOT PREREGISTERED; DATA BLOCKED; NO ORDERS.**

EXP-0005 is separate from EXP-0004. It must not import EXP-0004 outcomes, change
the locked structural hypothesis after observing returns, or be described as a
profitable strategy before prospective validation.

## Proposed fixed decision sequence

1. Use a fresh executable-price feed with bid/ask timestamps. Reject feed age
   above 10 seconds and reject crossed, zero, or abnormal spreads.
2. Determine H1/M30 context only from closed bars. Directional permission is
   LONG after a sell-side sweep plus bullish displacement/MSS, SHORT after a
   buy-side sweep plus bearish displacement/MSS. Otherwise abstain.
3. On M5/M1 require a retrace into the causal displacement FVG or breaker. Do
   not enter on the impulse candle and do not infer zones from later bars.
4. Simulate entry at the first later executable bid/ask quote after the decision,
   including spread, fixed commission, measured latency and adverse slippage.
5. Stops sit beyond the swept liquidity/structural invalidation, not at a fixed
   attractive distance. Reject if stop exceeds the pre-registered maximum or
   if target before opposing liquidity gives less than 1.5R after costs.
6. Permit at most one open gold exposure, one retry per session thesis and a
   daily loss veto. No averaging, martingale, rescue entries or parameter search.
7. Exclude scheduled tier-one releases within a fixed pre/post window and stop
   on abnormal spread/latency. Macro and flow may veto; they cannot manufacture
   a technical entry.

## Evidence required before implementation lock

- At least bid/ask quotes or trades fresh enough for the 10-second gate. One-minute
  delayed OHLC bars are insufficient to prove a scalp fill or its cost.
- Broker-specific symbol, contract size, minimum tick, commission, financing,
  trading sessions and rejection rules, all captured from the intended account.
- An outcome-free feed study covering normal, rollover and high-volatility hours.
- One primary endpoint and fixed development/holdout calendar with dependence-
  aware inference, missing-data rules and no interim acceptance.
- Paper/shadow validation before any micro-live consideration. Real-order routing
  remains out of scope until a separately approved risk and execution review.

Current Massive evidence is about 479 minutes stale against EXP-0004's 20-minute
gate and is therefore also unusable for this proposed 10-second scalp gate.
