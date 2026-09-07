# EXP-0004 — causal paper execution candidate

Status: **ENGINEERING_ONLY; not preregistered; formal verdict forbidden.**

This change fixes the mechanics found in the EXP-0003 audit. It preserves the
structural sweep/MSS/FVG/retest hypothesis and does not change, reopen, or merge
evidence from EXP-0001, EXP-0002, or EXP-0003. It is not evidence of profitability.

## Implemented mechanics

| Item | EXP-0004 rule |
| --- | --- |
| Information cutoff | Only intervals closed by the acquisition start enter the snapshot. |
| Receipt | Record completion of acquisition separately from request start. |
| Decision | Sample wall clock after feature extraction and settlement. Freshness is measured at that time. |
| Signal availability | Structural bar START + one minute; front contract only; latest structural candidate only. |
| Information age | Keep the existing 20-minute feed / 15-minute candidate limits. No relaxation to manufacture signals. |
| Conditional entry | Reserve the next strictly later full minute. DECISION contains no entry price. |
| Paper fill | In a later received snapshot, use the reserved minute's OPEN, on the same raw contract. This is an OHLC proxy, not an executable quote or actual trade. |
| Write delay | Veto if validation has already passed the reserved minute before append. Durable external timestamp anchoring remains an activation gate. |
| Exit | At fill + 5/15/30/60 minutes, use the CLOSE of the interval ending exactly there. |
| Gaps | No substitute interval or next-session price. Wait up to 24 hours after target close for observation; then seal MISSING. Data first seen beyond the deadline cannot rescue it. |
| Costs | Deduct assumed 0.35 USD/oz per round trip; also record 1.5x cost stress. These assumptions are not verified broker costs. |
| Exposure | Do not accept overlapping 60-minute GC exposure, including across contracts. Missing fills do not release the reserved window early. |
| Identity | Contract, direction and signal-availability timestamp; independent of changing rolling-window indices. |
| Roll | Fetch front plus every contract with unresolved fills or any unresolved horizon. Never join prices across contracts. |
| Provenance | Hash both raw response rows and normalized bars; verify snapshot before decisions. Reject malformed OHLC/volume and duplicate intervals. |
| Recovery | Separate EXP-0004 ledger; reject other experiment records. CLI requires explicit exclusive genesis creation; no silent reset. |

The system studies a directional holding-period return. It does not yet model
position sizing, stop execution, order queues, spread, partial fills or broker
latency. Bars with no trades are missing observations, not permission to invent
a fill. Primary and secondary horizons must not become four opportunities to
select whichever result looks best.

## Required before a prospective statistical launch

1. Freeze an executable validation policy and its code hash before collecting
   research outcomes: one primary 60-minute endpoint, sample/deadline stopping,
   missing-data handling, effect-size requirement and dependence-aware inference.
   A count of 200 alone is not a statistical acceptance criterion.
2. Fix a chronological holdout and prohibit tuning or repeated acceptance checks
   against it. Decide the calendar stopping date and allocation before launch;
   this engineering change does not invent an achieved sample or lock arbitrary
   numbers after looking at outcomes.
3. Seal the complete implementation manifest, including imported structural,
   provider, and ledger dependencies. Put independent run/tip anchors outside the
   mutable ledger and require a trusted expected tip during recovery. Hash-chain
   consistency alone cannot detect a complete rewrite or prefix truncation.
4. Run a real-data, outcome-free acquisition/latency check and establish observed
   feed recency. Existing HTTP access and stale bars do not establish a paid tier.
5. Activate a separate pinned scheduler/artifact stream only after those gates.
   The existing EXP-0003 scheduler is not changed by this candidate PR.

Until then, the runnable CLI is explicitly an **engineering dry run**, not a
preregistered EXP-0004 sample. Engineering ledgers must never be relabeled as
prospective statistical evidence.

## Verification and use

Run the scenario suite:

```sh
python -m pytest -q gold_cio_v9/tests/test_forward_v4.py
```

The suite covers delayed snapshots, future/incomplete bars, exact horizon ends,
missing fill/exit intervals, observation deadlines, replay idempotence, changed
candidate indices, exposure overlap, rolled contracts, snapshot tampering,
cross-experiment ledger rejection and processing-clock delay.

An explicitly authorized engineering run can use the existing repository
credential without putting it in command arguments:

```sh
PYTHONPATH=. python scripts/forward_v4_cycle.py \
  --output-dir forward_v4_artifacts \
  --ledger forward_v4_artifacts/engineering_ledger.jsonl \
  --engine-commit "$(git rev-parse HEAD)" --initialize
```

Omit `--initialize` on continuation. Preserve the ledger, raw snapshots and
acquisition metadata together. This PR supplies no automatic production launch.
