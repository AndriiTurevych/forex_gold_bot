# Gold CIO v9.1 — Rejection Constitution

This document is frozen before viewing EXP-0001 performance results. Its purpose is to prevent post-hoc redefinition of success criteria.

## 1. Scope freeze
Until EXP-0001 receives a formal ACCEPT or REJECT verdict, no new alpha engine, ICT feature family, execution feature, dashboard feature, or microstructure layer may be promoted into the core research path. The only permitted parallel work is: data integrity, point-in-time correctness, backtest/validation infrastructure, deterministic risk/position sizing, regression tests, and critical bug fixes.

## 2. Required validation path
EXP-0001 must complete the full path:
Historical Data -> Point-in-Time Features -> Candidate Generation -> Cost/Slippage Model -> Purged CV -> Embargo -> Walk-Forward -> Regime Holdout -> Untouched Final Holdout -> DSR -> PBO -> Final Verdict.

## 3. Hard no-go criteria
EXP-0001 is REJECTED if any of the following holds on the frozen OOS evaluation:
- Net OOS expectancy <= 0 after realistic costs.
- OOS profit factor < 1.30.
- Fewer than 200 independent OOS occurrences for the main promotion decision; 100-199 may remain exploratory only.
- Deflated Sharpe Ratio significance/probability fails the predefined significance threshold used by the validation engine.
- Probability of Backtest Overfitting >= 20% target threshold, unless the experiment is explicitly downgraded to exploratory and never promoted.
- Performance does not survive 1.5x transaction-cost stress.
- More than 30% of total OOS P&L is attributable to one month/session/regime bucket without a preregistered economic reason.
- Removing the top 3 profitable trades destroys positive expectancy or reduces PF below 1.0.
- Edge disappears under a small conservative slippage shock defined before the final holdout is opened.
- Final untouched holdout expectancy is non-positive.
- Material look-ahead, timestamp, session, data-quality, or fill-model contamination is discovered.

Any rejected experiment keeps its full record. Failed experiments are never deleted from the denominator of model-search history.

## 4. No rescue optimization
After EXP-0001 results are observed, thresholds, lookbacks, session windows, displacement thresholds, FVG definitions, stop/target logic, or filters may not be altered under EXP-0001. Any change creates a new preregistered experiment ID with a new untouched holdout.

## 5. Falsification-first stress battery
Before promotion, EXP-0001 must be tested against:
- 1.0x, 1.5x and 2.0x costs.
- Additional adverse slippage shock.
- Removal of top 1, top 3 and top 5 trades.
- Trend, range, high-volatility and low-volatility regimes.
- London vs NY AM vs macro-window segments.
- Year/month stability where sample allows.
- Delayed fills and one-bar-later execution stress where applicable.
- Broken/missing-data simulations for the pipeline, without using those runs as alpha evidence.

## 6. Diversification rule
If EXP-0001 is accepted, the next objective is not optimization of EXP-0001. The next objective is to discover 2-4 additional alpha families with low return correlation and distinct economic/market logic. No single setup should become the sole production alpha source.

## 7. Data truth rule
Microstructure/L2 alpha remains FROZEN unless genuine timestamped tick/L2 data with known quality and latency characteristics is available. Delayed or proxy data must never be presented or validated as live microstructure.

## 8. Position sizing independence
Position sizing is deterministic and independent from alpha conviction. AI/ML may recommend lower risk but may never exceed the hard risk ceiling. Volatility, drawdown and correlation scaling must reduce exposure when risk rises.

## 9. Shadow promotion gate
Research success does not imply live deployment. An accepted alpha must pass an extended SHADOW phase covering multiple regimes, including trend, range, and at least one material macro-volatility episode when feasible. Backtest-vs-shadow divergence above predefined tolerances triggers review or pause, not parameter rescue.

## 10. Model degradation rule
Production strategies must have explicit quantitative pause/de-risk rules based on rolling expectancy, PF, calibration and live-vs-shadow divergence. These thresholds are set before live deployment and cannot be relaxed during drawdown without a new governance decision and renewed validation.

## 11. Governance rule
Every environment promotion requires a checklist-based review: RESEARCH -> SHADOW -> MICRO LIVE -> LIVE. The same person may design and review the system, but the checklist, evidence bundle and final verdict must be immutable and auditable.

## Governing philosophy
A rejected strategy is a successful research outcome if it prevents capital from being allocated to a false edge. The project optimizes for truth, capital survival and reproducible evidence, not for preserving any favored trading idea.
