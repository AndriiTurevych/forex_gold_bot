# Gold CIO v9.1 — Backtest Runner + Validation Engine Specification

This pipeline is the only authority allowed to produce an EXP-0001 ACCEPT/REJECT verdict.

## 1. Data pipeline

Input: immutable raw tick/bar data and point-in-time features.

Hard prechecks before any run:
- event_time <= available_time for every feature record;
- no duplicate sequence/event records unless explicitly reconciled;
- gap detection with explicit exclusion flags; no silent interpolation;
- session/calendar version pinned into run metadata;
- futures contract/roll metadata pinned where applicable;
- dataset snapshot serialized deterministically and hashed as data_snapshot_hash.

Any failure in PIT integrity or calendar/version pinning aborts the run.

## 2. Label horizon model

Each candidate has a label interval [decision_time, label_end_time]. Purging must use the actual label_end_time, not a fixed generic bar count when horizons differ.

For EXP-0001, label_end_time is the maximum horizon required by the outcome labeler (currently 5/15/30/60 minutes; use the maximum configured horizon for purge calculations).

## 3. Purged contiguous k-fold CV

Default preregistration target for EXP-0001:
- k = 6 contiguous chronological folds;
- test folds remain contiguous;
- training observations whose label interval overlaps the test interval are purged;
- embargo after each test fold = max_label_horizon + 1% of total sample duration, rounded up to whole bars;
- no random shuffling.

Sensitivity report must also show k=5 and k=8, but the primary verdict uses the preregistered k=6 configuration.

## 4. Walk-forward engine

Primary walk-forward policy for EXP-0001: expanding window.

Sequence:
Train[t0:t1] -> Test[t1:t2]
Train[t0:t2] -> Test[t2:t3]
Train[t0:t3] -> Test[t3:t4]
...

Rules:
- no parameter retuning between test segments;
- each test segment is evaluated separately;
- overlapping/duplicate candidate signals are clustered before independent-sample counting;
- raw setup count and effective independent sample size are reported separately.

## 5. Cost and slippage model

Base-case headline metrics use realistic conservative costs, never frictionless costs.

Required scenarios:
- base realistic costs;
- 1.5x costs;
- 2.0x costs;
- event-window widening;
- delayed execution / latency shock;
- no impossible fills.

PF >= 1.30 is required on base realistic costs. Expectancy must remain positive at 1.5x costs.

## 6. Regime segmentation

Minimum dimensions:
- volatility: low / mid / high;
- trend: trend / range;
- session: Asia / London / NY;
- macro proximity: event-window / calm.

For each sufficiently sampled segment report: count, expectancy, PF, drawdown, win/loss distribution, MAE/MFE.

A major regime with materially negative expectancy and unacceptable drawdown is a hard fail unless a deterministic ex-ante regime filter was preregistered and independently validated.

## 7. Statistical validation

### DSR
- maintain trials_log for every tested strategy/configuration variant;
- DSR uses the true count/distribution of trials, including abandoned variants;
- hidden/forgotten trials are prohibited.

### PBO
- use Combinatorial Purged Cross-Validation (CPCV);
- evaluate rank degradation from in-sample to out-of-sample;
- target PBO < 20%.

## 8. Concentration diagnostics

Report both:
- top-5% P&L contribution share;
- Gini coefficient of trade P&L contribution.

Also rerun performance after removing the top 3 and top 5 trades. Concentration thresholds belong to the preregistered acceptance config and cannot be changed post-results.

## 9. Immutable trials log

Every run/configuration must persist:
- trial_id;
- parent_experiment_id;
- config_hash;
- code_commit_sha;
- data_snapshot_hash;
- feature_set_hash;
- calendar_version;
- cost_model_version;
- validation_config_hash;
- created_at;
- status;
- metrics artifact hash;
- verdict.

No trial can be deleted from the DSR/PBO denominator.

## 10. Automated verdict

The validation pipeline must persist metrics to the Evidence Ledger before any human review, then call the deterministic acceptance evaluator.

Humans may downgrade ACCEPT to REJECT for safety reasons. Humans may not upgrade REJECT to ACCEPT without registering a new experiment/version and rerunning the complete pipeline.
