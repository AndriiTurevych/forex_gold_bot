# EXP-0004 — causal paper execution candidate

Status: **IMPLEMENTED_NONBINDING_RESEARCH; ACTIVATION_BLOCKED_STALE_FEED.**

No prospective sample has started. Formal/live-trading verdicts remain forbidden.

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

## Validation and activation status — 2026-09-09

The executable protocol is `EXP-0004-PROTOCOL.json`. It fixes a 180-day calendar
from explicit prospective genesis: 90 days development, then 90 days untouched
holdout, with a 61-minute boundary embargo. Each partition requires at least
100 complete primary observations and 40 active days. These are minimum coverage
requirements, not a power calculation or promise of statistical significance.

Acceptance requires both partitions to pass: positive one-sided 95% lower
moving-block-bootstrap bound (14-calendar-day blocks, 10,000 deterministic
replicates), mean net return at least 0.10 USD/oz, profit factor at least 1.3,
and positive mean after 1.5x assumed costs. There is no early acceptance.
Any missing primary observation prevents acceptance. The evaluator recomputes
gross return from fill/exit records and rejects inconsistent times or contracts.
Block bootstrap inference is approximate and assumes historical blocks are
informative about the process; it cannot establish future executable profits.

The CLI enforces registered collection boundaries, refuses engineering-ledger
promotion, requires a matching engine/protocol lock, and requires an external
expected checkpoint on continuation. It writes the next checkpoint for separate
persistence. This detects truncation or rewriting relative to a trusted anchor;
it does not protect against someone rewriting both the ledger and its anchor.

Real-data preflight run 34342647327 retrieved 9,792 GCZ6 bars. At receipt on
2026-09-09 10:55 UTC the latest closed bar was 02:56 UTC: 479.6 minutes old.
`EXP-0004-DATA-PREFLIGHT.json` seals this observation and artifact identity.
**DATA_READY=false.** Account tier was not independently verified.

Prospective activation is blocked. It requires a fresh successful preflight,
an exact implementation commit/protocol lock and a separate durable checkpoint
stream whose trusted identity is passed into every restore. The automated
scheduler and its recovery must be exercised end to end with that stream before
calling the system operational. The existing EXP-0003 scheduler is unchanged.
No old or engineering outcomes may be imported into the new prospective sample.

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
