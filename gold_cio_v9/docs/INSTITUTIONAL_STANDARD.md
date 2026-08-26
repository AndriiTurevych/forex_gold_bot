# Gold CIO v9.1 — Institutional Research & Execution Standard

This document raises the target from a basic shadow-trading MVP to a production-compatible institutional research and execution core.

## Non-negotiable governing principles

1. AI may propose; Evidence may promote; Deterministic Risk may veto; nothing overrides Risk.
2. No production decision may depend on unavailable future information.
3. Every signal must be reproducible from an immutable point-in-time snapshot.
4. Research, risk, execution, and operations must fail independently rather than cascade.
5. Any strategy or model change requires a new version/hash and renewed validation.

## Core architecture

Event Bus -> Data Quality -> Point-in-Time Feature Store -> Alpha Engines -> Challenger Registry -> Meta-Labeler -> Deterministic Risk -> Execution State Machine -> Broker Reconciliation -> Shadow/Live Ledger -> Monitoring/Audit.

## Mandatory production contracts

### Data contract
- source_id
- instrument_id
- event_time
- receive_time
- sequence_id
- bid/ask/last/volume fields where applicable
- source quality state
- stale threshold
- session/calendar version
- corporate/contract roll metadata where applicable

### Feature contract
- feature_name
- feature_version
- event_time
- available_time
- source lineage
- transformation hash
- null/missing policy

### Signal provenance contract
Every candidate/signal must persist:
- signal_id
- decision_time
- data_snapshot_hash
- feature_set_hash
- strategy_name/version/hash
- model version/hash when ML is used
- regime state
- direction
- entry/stop/target
- expected R
- cost/slippage assumptions
- risk decision
- execution decision
- challenger/baseline attribution

## Research validity gate
A strategy cannot leave research unless it passes:
- preregistered hypothesis
- purged CV and embargo
- walk-forward validation
- regime holdout
- untouched final holdout
- DSR / multiple-testing correction
- PBO target below defined threshold
- positive OOS expectancy after costs
- minimum OOS sample requirement
- no concentration of P&L in one regime/month/session
- 1.5x cost stress minimum; 2x reported

## Trading validity gate
Before shadow promotion:
- fill model tested
- conservative spread/slippage
- latency assumptions
- bar-ambiguity policy
- no impossible fills
- session/calendar/DST correctness
- roll handling for futures
- partial-fill logic
- cancellation/replace logic
- duplicate event/order protection

## Operational validity gate
Before any real-money deployment:
- idempotent order state machine
- broker/account reconciliation
- restart/recovery replay
- stale-data kill switch
- feed disagreement veto
- max order-size limits outside AI
- hard daily/weekly drawdown locks
- event lock policy
- connectivity degradation policy
- heartbeat monitoring
- alerting and audit logs
- secret isolation; no withdrawal permissions

## Three independent environments

RESEARCH: unrestricted experimentation, never routes orders.
SHADOW: live data and simulated orders, no capital at risk.
LIVE: production-only approved versions with immutable config and risk limits.

No direct RESEARCH -> LIVE path is allowed.

## Champion–Challenger registry

Baseline CIO remains Champion until a challenger proves incremental value.
Current challengers:
- #1 Obsidian
- #2 Quantitative SMC

A challenger must beat the baseline on precision and/or expected value after costs without unacceptable drawdown or regime fragility.

## Execution state machine

Candidate -> RiskChecked -> Approved -> Submitted -> Acknowledged -> PartiallyFilled/Filled -> Managed -> Closed -> Reconciled.

Illegal transitions must fail closed.

## Kill conditions

The system must stop new orders when any of these occur:
- stale or missing critical feed
- cross-feed disagreement above threshold
- broker position mismatch
- daily/weekly risk limit breach
- abnormal spread/slippage
- corrupted clock/session state
- model/config hash mismatch
- duplicate order detection
- unreconciled order state

## Observability

Track in real time:
- feed latency/staleness
- feature freshness
- strategy decision counts
- TAKE/SKIP rate
- risk veto reasons
- order/fill latency
- slippage vs model
- live vs shadow divergence
- calibration drift
- rolling expectancy/PF/MAE/MFE
- per-regime attribution

## Promotion philosophy

The system is not considered ready because it runs. It is ready only when it is statistically valid, operationally resilient, fully auditable, and safe under failure.
