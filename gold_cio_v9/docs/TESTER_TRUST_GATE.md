# Gold CIO Tester Trust Gate

EXP-0001 must not run for a binding ACCEPT/REJECT verdict until all five gates below pass.

## Gate 1 — Synthetic leakage detection
- Inject an intentionally future-looking feature.
- Pipeline must hard-fail the run and record the violation.
- A silent pass is a critical defect.

## Gate 2 — Deterministic replay
- Same dataset snapshot hash + same config hash + same code/model hash + same random seed must produce identical metrics and verdict.
- Any non-determinism blocks promotion.

## Gate 3 — Complete trials registry
- Every experimental configuration attempt is logged before results are inspected.
- Debug/dummy runs that alter tested strategy/config space are included in the trial count used for DSR deflation.
- Deleted/failed attempts remain in the immutable registry.

## Gate 4 — Known-answer synthetic verdict tests
The automated acceptance engine must correctly handle at minimum:
- pure-noise dataset -> REJECT;
- intentionally embedded robust synthetic edge -> ACCEPT, assuming all preregistered thresholds are met;
- edge concentrated in a few outliers -> REJECT or concentration gate failure;
- edge that disappears under realistic costs -> REJECT;
- edge with regime fragility -> REJECT where sufficient segment sample exists.

## Gate 5 — Version-controlled validation configuration
No validation-critical parameter may be edited interactively during a binding run.
The following must be pinned in version control and included in the run hash:
- CV folds;
- purge logic;
- embargo length;
- label horizons;
- walk-forward mode/window;
- base transaction-cost model;
- cost stress multipliers;
- delayed-execution stress;
- DSR significance threshold;
- PBO threshold;
- PF/expectancy/sample/concentration thresholds;
- regime definitions;
- random seed.

Any change requires a new commit/config hash and a new run. It may not mutate an existing run.

## Binding rule
`CAN_TRUST_TESTER = YES` only when all five gates pass in CI.

Until then:
- Engineering readiness may increase.
- Proven alpha readiness remains 0%.
- EXP-0001 results are diagnostic only and cannot receive a binding ACCEPT verdict.
