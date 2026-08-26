# Gold CIO v9.1 — Edge-First Roadmap

This roadmap explicitly prioritizes proof of edge over architectural completeness.

## Priority 1 — Prove or reject EXP-0001

Finish the historical backtest runner and validation engine before expanding live execution.

Mandatory sequence:
1. point-in-time candidate generation
2. realistic fill/cost model
3. purged CV
4. embargo
5. walk-forward
6. regime holdout
7. untouched final holdout
8. DSR / multiple-testing correction
9. PBO
10. stress costs at 1.0x / 1.5x / 2.0x

No-go rule: if EXP-0001 fails the predefined statistical gate, reject it. Do not patch thresholds after observing results. Any material change requires a new experiment ID.

## Priority 2 — Diversify alpha

Target 3–5 statistically distinct alpha families with low realized correlation of trade outcomes / P&L drivers.

Current streams:
- Baseline CIO
- EXP-0001 Liquidity Sweep Reversal
- Challenger #1 Obsidian
- Challenger #2 Quantitative SMC

Additional alpha families should only be added after preregistration and independent validation.

## Priority 3 — Data truthfulness

Microstructure stays FROZEN until genuine quality tick/L2 data is available.

Proxy data must never be labeled as LIVE microstructure.

Before shadow promotion, inject deliberately broken data to test:
- stale timestamps
- crossed / absurd quotes
- missing sequence ranges
- out-of-order events
- cross-feed divergence
- duplicate events

## Priority 4 — Conservative execution economics

Backtests must model stressed, not average, trading conditions.

Mandatory scenarios:
- normal spread/slippage
- 1.5x costs
- 2.0x costs
- macro-event spread expansion
- latency spikes
- adverse slippage
- impossible-fill rejection

## Priority 5 — Explicit position sizing

Risk approval and position sizing are separate concerns.

Position sizing must consider:
- risk budget per trade
- stop distance
- realized volatility / vol targeting
- fractional Kelly ceiling
- concurrent exposure
- correlation-adjusted exposure across XAU/GC/SI
- portfolio drawdown state
- liquidity / spread state

No AI or strategy layer may directly set size outside the sizing contract.

## Priority 6 — Honest shadow phase

Shadow must run long enough to span multiple regimes, including trend/range, high/low volatility and at least one macro shock if possible.

Shadow-to-live divergence is a stop signal requiring investigation, not tuning by default.

## Priority 7 — Automatic degradation controls

Predefine numeric auto-pause/de-risk criteria before live deployment.

Examples of monitored degradation:
- rolling net expectancy <= 0
- rolling PF below threshold
- calibration deterioration
- excessive slippage vs model
- repeated feed/data-quality vetoes
- regime concentration
- live/shadow divergence

Thresholds must be preregistered per strategy version.

## Priority 8 — Independent review discipline

Because development and trading oversight are concentrated, every environment transition requires a checklist-based review.

Required transitions:
- Research -> Shadow
- Shadow -> Micro Live
- Micro Live -> Live

No transition is allowed on discretionary confidence alone.
