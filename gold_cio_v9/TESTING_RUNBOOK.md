# Gold CIO v9 — EXP-0001 Testing Runbook

## Purpose

This runbook defines the only supported path from external evidence to an EXP-0001 result. The order is intentionally fail-closed so that dataset, contract selection, macro calendar, costs, code version and governance are fixed before any strategy outcome is generated.

## Locked experiment identities

- Experiment: `EXP-0001`
- Implementation: `EXP-0001-BASELINE-POLICY-V5`
- Validation: `EXP-0001-VALIDATION-POLICY-V5`
- Primary instrument: raw GC futures contracts
- Frequency: 1 minute
- Horizons: 5, 15, 30, 60 wall-clock minutes
- Promotion horizon: 60 minutes
- Roll policy: immutable outright GC contract master + highest completed prior-session volume, no current-session volume, no OI hindsight, no adjusted continuous prices
- Roll expiry buffer: 5 calendar days
- Additional roll blackout: 0 bars; causal context restarts independently per raw contract
- Base all-in cost: 0.35 GC price points / 35 USD per contract round trip
- Mandatory stress: 1.5x = 0.525 points / 52.50 USD per contract

## Required external evidence files

1. `bars.jsonl` — globally chronological authoritative raw GC 1m bars. Every row must include instrument, contract, timezone-aware event_time, OHLC, volume, quality_state, source_id, roll_method and is_roll_window.
2. `contract_master.json` — immutable outright GC contract specifications and optional declared master_hash.
3. `lineage.json` — exact roll decisions, prior completed-session volume universe for every decision day, fetch windows, dataset hash, contract-master hash and replay-verifiable lineage hash.
4. `macro_calendar.json` — PIT high-impact US calendar covering the complete bar interval, with external source identity, timezone-aware event_time/known_at and only preregistered categories: FOMC, FED_CHAIR, CPI, CORE_PCE, NFP, RETAIL_SALES.

## Zero-outcome preparation

Build the bundle. The builder automatically injects the locked V5 costs; no caller cost override exists.

```bash
python scripts/build_exp0001_bundle.py \
  --bars bars.jsonl \
  --lineage lineage.json \
  --contract-master contract_master.json \
  --macro-calendar macro_calendar.json \
  --output exp0001_bundle.json
```

Then run preflight. This does not generate signals, trades, PnL or validation statistics.

```bash
python scripts/preflight_exp0001.py \
  --bundle exp0001_bundle.json \
  --output exp0001_readiness.json
```

Do not proceed unless `ready=true` and `failed_checks=[]`.

## Non-binding full evidence test

A non-binding test is permitted once the bundle passes preflight and both repository CI suites are green for the tested commit.

```bash
python scripts/run_exp0001_formal.py \
  --mode nonbinding \
  --bundle exp0001_bundle.json \
  --git-commit <exact-head-sha> \
  --trials evidence/trials.jsonl \
  --ledger evidence/ledger.jsonl \
  --output evidence/exp0001_result.json
```

The trial is registered before strategy outcomes are generated. Base and 1.5x-cost evidence books are produced, then regime labels, chronological development/OOS/untouched-holdout validation, DSR/PBO, concentration checks and tri-state verdict. The Evidence Ledger is persisted before the result object is returned.

## Binding test

A binding verdict is forbidden until repository governance is enabled for `gold-cio-v9` and an attestation for the exact tested commit proves:

- branch protection enabled;
- required status checks enforced;
- Gold CIO v9 CI green;
- Tester Trust Gate green;
- attestation head SHA exactly equals the tested commit.

Run binding mode only with that attestation:

```bash
python scripts/run_exp0001_formal.py \
  --mode binding \
  --governance-attestation governance.json \
  --bundle exp0001_bundle.json \
  --git-commit <exact-head-sha> \
  --trials evidence/trials.jsonl \
  --ledger evidence/ledger.jsonl \
  --output evidence/exp0001_binding_result.json
```

## Promotion gate

EXP-0001 can be accepted only through the deterministic tri-state constitution. Among the mandatory conditions are positive net OOS expectancy, OOS PF >= 1.30, at least 200 resolved OOS setups on the primary 60m horizon, positive untouched holdout expectancy, stable walk-forward windows, DSR pass, PBO <= 20%, survival at 1.5x costs, concentration controls, no catastrophic sufficiently-sampled regime, data integrity pass and no post-result parameter edits.

Any failure that represents insufficient evidence rather than demonstrated negative edge must remain `INSUFFICIENT_DATA`; it may not be manually promoted to ACCEPT.

## Current real-data inventory

The Massive workspace acquisition inventory currently records 485,199 raw GC 1m bars across nine causal-front contract segments from 2025-04-03 through 2026-08-27, with no observed bad OHLC rows, negative volume rows or within-contract duplicate timestamps. The inventory is explicitly not formal evidence until materialized into the four external evidence files above and successfully bundled/preflighted.

## Hard rule

Never inspect strategy PnL to decide contract roll methodology, costs, horizons, macro categories, threshold values or validation rules. Any such change after outcomes requires a new experiment or explicit new policy version and cannot retroactively improve EXP-0001.
