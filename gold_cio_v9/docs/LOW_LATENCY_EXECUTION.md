# Gold CIO v9.1 — Low-Latency Execution Standard

## Principle

Think continuously. Decide fast. Execute deterministically.

The critical execution path must not wait for LLM inference, web requests, research pipelines, or expensive feature recomputation. Heavy context is computed continuously before a trigger appears. The trigger path consumes only fresh cached context and deterministic gates.

## Runtime shape

1. Continuous context loop
   - HTF regime
   - liquidity map / location
   - macro permission state
   - volatility state
   - model health
   - data-quality state
   - risk budget

2. Trigger loop
   - liquidity sweep / displacement / MSS / FVG-retest event
   - alpha qualification
   - current executable price

3. Deterministic fast path
   - context freshness
   - trigger freshness
   - data-quality VETO
   - model-health VETO
   - risk VETO
   - regime/location/macro permission
   - alpha/meta-label TAKE/SKIP
   - entry degradation check

4. Order path
   - deterministic position sizing
   - broker order construction
   - submit
   - acknowledgement/reconciliation

The LLM/context engine is explicitly outside steps 3 and 4.

## Initial engineering latency SLOs

These are runtime engineering targets, not alpha assumptions and not part of EXP-0001 historical validation:

- trigger -> deterministic decision: <= 50 ms
- decision -> order submit: <= 25 ms
- signal -> order submit: <= 100 ms
- trigger older than 250 ms: STALE
- precomputed context older than 1000 ms: STALE
- adverse entry degradation above 0.30 GC points: STALE

These defaults are deliberately conservative placeholders for shadow engineering. They must be measured on the actual feed/broker path before Micro Live. Changing them does not change EXP-0001 research outcomes.

## Fail-closed rules

A candidate cannot be executed when:

- trigger is stale
- context is stale
- decision latency budget is breached
- executable entry degraded beyond the allowed amount
- data-quality veto is active
- model-health veto is active
- risk veto is active

A stale setup is not chased. A late correct signal is still a bad execution.

## Required telemetry

Every executable candidate must record monotonic timestamps for:

- trigger detected
- decision start/end
- sizing start/end
- order-submit start/end
- broker acknowledgement

Required derived metrics:

- trigger-to-decision latency
- decision-to-order latency
- total signal-to-order latency
- theoretical vs executable entry degradation
- broker acknowledgement latency
- stale-signal rate
- latency-veto rate
- slippage vs backtest model

## Promotion rule

Before Shadow -> Micro Live, latency telemetry must demonstrate that the production path does not materially consume the tested edge. Persistent latency or entry-degradation breaches require architecture or infrastructure correction, not looser gates.
