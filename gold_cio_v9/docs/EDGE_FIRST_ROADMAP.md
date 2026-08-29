# Gold CIO v9.1 — Edge-First Roadmap

This roadmap prioritizes proof of edge, reproducibility, and capital preservation over architectural completeness.

## Current state

- Research architecture: built.
- EXP-0001 implementation policy: locked V5.
- EXP-0001 validation policy: locked V5.
- Historical evidence acquisition: implemented, pending Massive repository secret.
- Formal nonbinding workflow: implemented and fail-closed.
- Binding governance: blocked until branch protection is enabled and verified.
- Proven alpha: none until EXP-0001 completes on authoritative GC evidence.

## Phase 0 — Infrastructure closure

Required before formal outcomes:
1. MASSIVE_API_KEY exists as a GitHub Actions repository secret.
2. Massive Futures entitlement check succeeds.
3. Gold CIO v9 CI succeeds.
4. Tester Trust Gate succeeds.
5. Formal workflow contract tests succeed.

Binding-only additional requirement:
6. gold-cio-v9 branch protection enabled with required Gold CIO v9 CI and Tester Trust Gate checks.

No strategy threshold may be changed to solve infrastructure failures.

## Phase 1 — Authoritative GC evidence

Acquire raw 1-minute GC contract sessions for the preregistered evidence interval.

Data rules:
- raw outright contracts only;
- no continuous adjusted series;
- no silent interpolation;
- causal front selection uses completed prior-session volume;
- immutable contract master;
- session membership follows session_end_date semantics;
- explicit lineage and dataset hashes;
- invalid, duplicate, cross-contract, or malformed rows fail closed.

Output:
- bars.jsonl
- lineage.json
- contract_master.json
- acquisition_summary.json

## Phase 2 — Immutable evidence bundle

Seal authoritative bars, acquisition lineage, contract master, PIT macro calendar, locked costs, and policy identities into one canonical evidence bundle.

Any modification must change the corresponding hash. The bundle must not depend on strategy outcomes.

## Phase 3 — Zero-outcome TEST_READY gate

Run preflight before strategy outcomes are generated.

Required checks include:
- policy identity;
- locked costs;
- dataset hash;
- lineage hash;
- contract-master hash;
- macro-calendar hash and coverage;
- source identities;
- chronological integrity;
- contract order and roll parameters;
- evidence coverage.

If TEST_READY is false, EXP-0001 does not run.

## Phase 4 — EXP-0001 formal nonbinding test

Locked hypothesis sequence:
HTF Location -> Liquidity Sweep -> Displacement -> MSS -> FVG/IFVG Retest -> Entry -> Opposing Liquidity.

Primary promotion horizon: 60 minutes.
Secondary diagnostics: 5, 15, 30 minutes.
No best-horizon post-hoc selection is allowed.

Validation stack:
1. chronological development/OOS/untouched holdout partitioning;
2. purged cross-validation;
3. 60-minute embargo;
4. walk-forward validation;
5. regime diagnostics;
6. deflated Sharpe;
7. probability of backtest overfitting;
8. concentration diagnostics;
9. realistic base costs;
10. 1.5x mandatory cost survival;
11. 2.0x diagnostic stress.

Primary acceptance expectations include positive net OOS expectancy, OOS PF >= 1.30, sufficient independent resolved OOS occurrences, acceptable PBO, and no disqualifying concentration or data-resolution failure.

## Phase 5 — Machine verdict

Only three outcomes are valid:

### ACCEPT
The preregistered hypothesis survives all mandatory gates. Freeze the accepted research version and move to forward shadow validation.

### REJECT
Close EXP-0001. Do not rescue it by changing thresholds after seeing outcomes. Any material new hypothesis becomes a new experiment ID.

### INSUFFICIENT_DATA
Do not call the strategy good or bad. Extend only evidence/data coverage where allowed without changing the hypothesis.

All formal runs must register the trial and persist the evidence-ledger verdict before returning the result.

## Phase 6 — Shadow

Only after ACCEPT.

Validate the complete real-time path without capital:
Market Data -> PIT Features -> Signal -> TAKE/SKIP -> Risk Gate -> Sizing -> Simulated Execution -> Reconciliation.

Shadow objectives:
- confirm timing equivalence to research;
- measure spread/slippage/latency;
- observe multiple market regimes;
- validate restart and reconciliation behavior;
- detect live-data quality failures;
- establish forward expectancy and calibration.

Promotion requires a preregistered shadow acceptance checklist. Divergence from historical behavior is investigated, not tuned away by default.

## Phase 7 — Micro Live

Only after shadow promotion.

Use deliberately small risk. The purpose is execution validation, not return maximization.

Verify:
- signal-to-order latency;
- fill quality versus model;
- stops and targets;
- partial fills;
- disconnect/restart recovery;
- broker reconciliation;
- realized transaction costs;
- risk veto enforcement.

Any material execution divergence can demote the strategy to shadow.

## Phase 8 — Champion

An accepted historical strategy that also survives shadow and micro-live becomes the production Champion.

Production architecture may add regime routing, meta-labeling, flow/context inputs, abstention, risk vetoes, and capital allocation only if they preserve or improve measured out-of-sample/live performance. No layer may bypass deterministic risk controls.

## Phase 9 — Champion–Challenger research

Future changes are independent experiments, not edits to accepted history.

Examples:
- SMT confirmation;
- DXY confirmation;
- macro exclusions;
- session specialization;
- order-flow proxy;
- alternative ICT sequence variants.

Each challenger is preregistered, evaluated OOS, and promoted only on measurable improvement in expectancy, calibration, drawdown, or precision.

## Phase 10 — Capital scaling and degradation control

Capital scaling is earned by stable evidence. It is never driven by confidence alone.

Before live scaling, preregister:
- per-trade risk ceilings;
- portfolio exposure ceilings;
- rolling expectancy degradation triggers;
- PF deterioration triggers;
- excessive slippage triggers;
- data-quality veto thresholds;
- drawdown de-risking rules;
- automatic shadow-demotion criteria.

Scaling must be reversible. Deterioration reduces risk before any attempt to increase complexity.

## Non-negotiable research constitution

1. No outcome-driven edits to EXP-0001.
2. No hidden best-horizon selection.
3. No transfer of an XAUUSD verdict to GC without separate evidence.
4. No adjusted-continuous futures for ICT absolute-level evidence.
5. No AI layer may bypass deterministic risk, sizing, or governance gates.
6. No binding verdict without verified branch protection and required checks.
7. No profitability claim before authoritative formal evidence exists.
8. Every material future strategy change receives a new experiment identity.
