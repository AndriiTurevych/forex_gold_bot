# Gold CIO v9.1 — Rejection Constitution v2

This document is pre-committed before EXP-0001 results are reviewed. Its purpose is to prevent hindsight redefinition of success criteria.

## 1. Independence of OOS setups

A nominal count of 200 setups is not sufficient by itself.

An OOS setup counts toward the minimum only if the evaluation sample also satisfies diversification requirements across time, session and regime:

- overlapping or mechanically duplicated signals are de-duplicated;
- concurrent signals caused by the same underlying market event are clustered and counted conservatively;
- no single calendar month may contribute more than 25% of accepted OOS observations;
- no single session bucket may contribute more than 60% unless the strategy is explicitly session-specific and preregistered as such;
- no single volatility/trend regime may contribute more than 60% of accepted OOS observations;
- at least three materially different market-regime buckets must be represented before promotion;
- effective sample size must be reported in addition to raw setup count when serial dependence is detected.

Target: >=200 raw OOS setups and a sufficiently large effective independent sample after clustering/dependence adjustment.

## 2. Costs standard

The base-case performance must use realistic, conservative transaction costs. Optimistic/frictionless costs are never the headline case.

Required outputs:
- Base: realistic spread + commission + slippage assumptions;
- Stress 1.5x: all modeled execution frictions scaled by 1.5;
- Stress 2.0x: all modeled execution frictions scaled by 2.0;
- event-window stress: widened spread/slippage around high-impact macro windows where applicable;
- latency shock: delayed entry simulation.

PF >=1.30 must be achieved on the realistic base-cost scenario, not on optimistic costs. The strategy must remain positive-expectancy at 1.5x costs. 2.0x is reported as a robustness diagnostic and must not be hidden.

## 3. Regime rule

Aggregate profitability is not sufficient if a strategy has a structurally destructive regime.

For preregistered core regimes, each segment must be evaluated separately. Promotion requires:
- no major regime with materially negative expectancy and unacceptable drawdown;
- no regime whose losses dominate total risk budget;
- no hidden dependence on one narrow regime for the majority of profits.

A small mildly negative segment may be tolerated only if it is explicitly identifiable ex ante, safely gated by a deterministic regime filter, and that filter itself is validated without hindsight. Otherwise the result is REJECT.

## 4. Automatic ACCEPT / REJECT authority

The formal decision must be produced by deterministic code before any manual discussion.

Required process:
1. Freeze experiment config and hashes.
2. Run validation pipeline.
3. Write all metrics to the immutable evidence ledger.
4. Run deterministic acceptance evaluator.
5. Persist ACCEPT / REJECT and failed criteria.
6. Only then review or discuss the result.

Humans may reject an automatic ACCEPT for additional safety reasons. Humans may not convert an automatic REJECT into ACCEPT without registering a new experiment/version and rerunning the full process.

## 5. EXP-0001 hard gates

Unless amended before first result review, EXP-0001 requires all of the following:

- net OOS expectancy > 0 after realistic base costs;
- OOS profit factor >= 1.30 at realistic base costs;
- >=200 raw OOS setups plus acceptable effective independence/diversification;
- walk-forward performance not dependent on a single fold;
- untouched final holdout expectancy > 0;
- Deflated Sharpe statistically acceptable under the preregistered multiple-testing context;
- PBO < 20% target;
- positive expectancy at 1.5x costs;
- robustness after removing top 3 and top 5 trades;
- no single month/session/regime explaining an excessive share of total P&L;
- no catastrophic regime segment;
- no material data leakage, impossible fills, session/calendar error or label ambiguity;
- no post-result parameter edits.

Failure of any hard gate => REJECT.

## 6. Anti-rescue rule

A rejected experiment is not tuned in place.

Any change to thresholds, lookbacks, session definitions, feature set, entry logic, stop/target logic, cost assumptions or regime filters creates a new experiment ID and restarts validation from the beginning.

A failed EXP-0001 is a valid research outcome, not a project failure.
