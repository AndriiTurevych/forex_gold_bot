# Gold CIO v9.1 — Production Readiness Backlog

Purpose: exhaustive pre-production control list for moving from validated research to reliable shadow, micro-live and live trading. This backlog does not alter EXP-0001 alpha logic.

Status legend: DONE = implemented/tested in repo; PARTIAL = primitive exists but production integration remains; TODO = not yet implemented; EXTERNAL = depends on broker/exchange/infrastructure/access.

## 1. Alpha and research integrity
- DONE preregistered hypothesis and locked experiment identity
- DONE point-in-time feature/event semantics
- DONE purged CV, embargo, walk-forward, holdout framework
- DONE DSR/PBO and multiple-testing discipline
- DONE cost stress 1.0x/1.5x/2.0x
- DONE ambiguity handling for same-bar target/stop
- DONE no post-outcome tuning rule
- TODO formal real-GC EXP-0001 evidence run
- TODO independent replication after first ACCEPT
- TODO challenger correlation / incremental-edge tests before portfolio use

## 2. Market-data integrity
- DONE causal GC contract selection and roll handling
- DONE session-aware historical acquisition
- DONE data lineage and immutable evidence bundle
- DONE stale-data and feed-agreement risk concepts
- TODO production real-time primary feed adapter
- TODO independent secondary feed for cross-check
- TODO sequence-gap detection
- TODO duplicate/out-of-order event detection
- TODO crossed/absurd quote detection
- TODO frozen/stale bid-ask detection
- TODO exchange halt/session-state handling
- TODO market-data reconnect replay/gap fill
- TODO feed failover policy with explicit source priority
- TODO tick-size/price-band validation before signal/execution

## 3. Time and clock integrity
- PARTIAL monotonic timestamps used for latency arithmetic
- PARTIAL deterministic clock-drift operational veto exists
- TODO NTP/PTP production synchronization policy
- TODO independent clock-health monitor
- TODO wall-clock vs monotonic correlation audit
- TODO timezone/DST/session boundary production tests
- TODO fail-closed behavior when time source becomes uncertain

## 4. Fast decision path
- DONE heavy context kept outside critical execution path
- DONE deterministic TAKE/SKIP/STALE/VETO fast path
- DONE trigger/context freshness controls
- DONE adverse entry-degradation veto
- DONE initial signal-to-order engineering budgets
- TODO pre-allocation / object-allocation profiling
- TODO p50/p95/p99/p99.9 latency distribution telemetry
- TODO latency jitter alarms, not only average latency
- TODO CPU scheduling/contention tests
- TODO GC pauses / Python runtime pause measurement
- TODO network path RTT measurement to broker gateway
- TODO capacity test under burst event rates

## 5. Order lifecycle and broker state
- DONE deterministic order-state primitive
- DONE explicit partial-fill and cancel-race transitions
- DONE UNKNOWN order state that blocks normal trading until recovered
- TODO production broker adapter
- TODO broker-native client-order-id mapping
- TODO cancel/replace semantics per broker
- TODO order reject reason taxonomy
- TODO exchange/broker throttle handling
- TODO order acknowledgement timeout handling
- TODO late fill after cancel handling
- TODO unsolicited broker/exchange event handling
- TODO Good-Till/Day/IOC/FOK policy validation
- TODO stop/stop-limit/market order semantic validation with actual broker

## 6. Idempotency and duplicate prevention
- DONE deterministic order-key primitive
- DONE process-local duplicate registry reference implementation
- TODO durable idempotency store surviving restart
- TODO atomic check-and-submit transaction boundary
- TODO idempotency across active/passive failover nodes
- TODO broker-side duplicate-order verification

## 7. Reconciliation and unknown-state recovery
- PARTIAL position-mismatch operational veto exists
- TODO real-time broker position reconciliation
- TODO open-order reconciliation
- TODO cash/margin reconciliation
- TODO fills/executions reconciliation
- TODO expected-vs-broker average price reconciliation
- TODO start-of-day reconciliation gate
- TODO post-reconnect reconciliation gate
- TODO end-of-day reconciliation report
- TODO UNKNOWN state recovery protocol before unkill

## 8. Risk controls and kill architecture
- DONE deterministic per-trade risk gate
- DONE daily/weekly drawdown locks
- DONE spread/data/feed/event vetoes
- DONE software kill-switch state in operational gate
- TODO max gross/net position limits
- TODO max order quantity/notional limits
- TODO max orders/messages per second
- TODO max open orders
- TODO max cancel/replace rate
- TODO max loss per strategy/session/day/week
- TODO portfolio exposure and correlated-risk limits
- TODO margin headroom minimum
- TODO gap-risk reserve
- TODO independent watchdog process capable of blocking new orders
- EXTERNAL broker/FCM emergency kill capability
- EXTERNAL CME Globex Kill Switch / risk-tool permissions where applicable
- TODO documented manual emergency procedure and escalation tree
- TODO controlled unkill requiring reconciled state

## 9. Execution economics
- DONE conservative historical cost model
- DONE entry-degradation veto primitive
- PARTIAL slippage operational veto exists
- TODO live spread capture at signal and fill
- TODO implementation shortfall measurement
- TODO decision-price -> submit-price -> ack-price -> fill-price attribution
- TODO partial-fill weighted slippage
- TODO queue-position uncertainty for passive orders
- TODO gap-through-stop model
- TODO macro-event spread/slippage stress model
- TODO latency-induced opportunity loss measurement
- TODO missed-fill and opportunity-cost accounting
- TODO evidence that realized execution does not consume tested alpha

## 10. Position sizing and portfolio arbitration
- DONE sizing separated from alpha/risk permission
- TODO production sizing contract bound to broker instrument metadata
- TODO GC/MGC conversion and contract multiplier checks
- TODO volatility-adjusted ceiling
- TODO liquidity-adjusted ceiling
- TODO margin-aware ceiling
- TODO concurrent-position cap
- TODO conflicting BUY/SELL alpha arbitration
- TODO signal priority when multiple setups compete for same risk budget
- TODO correlation-adjusted allocation across GC/XAU/SI if portfolio expands
- TODO fractional-Kelly ceiling only after sufficient live evidence

## 11. Shadow/live twin and drift detection
- TODO deterministic shadow twin running beside live
- TODO identical signal IDs across shadow/live branches
- TODO theoretical vs shadow vs live fill comparison
- TODO live/shadow divergence limits
- TODO automatic de-risk or pause on persistent divergence
- TODO rolling expectancy/PF/calibration degradation rules
- TODO regime-concentration drift rules
- TODO execution-quality drift rules

## 12. Reliability, restart and disaster recovery
- TODO append-only durable event journal
- TODO periodic state snapshots
- TODO deterministic replay from last snapshot+journal
- TODO crash during order submission test
- TODO crash after broker fill but before local acknowledgement test
- TODO restart with open position test
- TODO restart with open/cancel-pending order test
- TODO network partition test
- TODO broker outage test
- TODO primary feed outage/failover test
- TODO disk-full/logging failure test
- TODO corrupted state/snapshot test
- TODO active/passive deployment design if live capital justifies it
- TODO recovery-time objective and recovery-point objective

## 13. Observability and SRE
- PARTIAL latency trace exists
- TODO p50/p95/p99/p99.9 latency dashboard
- TODO feed freshness dashboard
- TODO order-state dashboard
- TODO broker connectivity heartbeat
- TODO rejection/partial-fill/slippage dashboards
- TODO risk-veto reason distribution
- TODO system health score independent of alpha
- TODO alert severity taxonomy
- TODO pager/escalation policy for real-money phase
- TODO alert deduplication and storm protection
- TODO immutable audit-log export

## 14. Security and access control
- TODO least-privilege broker credentials
- TODO trading permission without withdrawal permission
- TODO secret manager / rotation policy
- TODO separate research/shadow/live credentials
- TODO MFA and recovery ownership documentation
- TODO no secrets in logs/artifacts
- TODO dependency and supply-chain scanning
- TODO pinned production dependencies/images
- TODO signed/reproducible release artifact
- TODO restricted production configuration changes

## 15. Release and change governance
- DONE experiment immutability discipline
- DONE CI/test gates
- TODO protected gold-cio-v9 or dedicated production branch
- TODO required CI/trust checks before merge
- TODO tagged immutable releases
- TODO explicit approved-version registry for LIVE
- TODO configuration hash at runtime
- TODO rollback package for every production release
- TODO canary/shadow release before live promotion
- TODO two-person/review checklist for live-risk changes when practical

## 16. Exchange/broker operational specifics
- EXTERNAL confirm exact broker/FCM and CME routing path
- EXTERNAL confirm account permissions, exchange entitlements and market-data licensing
- EXTERNAL document broker order throttles and reject codes
- EXTERNAL document CME/broker session recovery behavior
- EXTERNAL confirm emergency kill mechanisms and who can invoke them
- EXTERNAL verify exchange maintenance/holiday/session calendars
- EXTERNAL verify position/margin/liquidation rules for actual account

## 17. Testing that must happen before Micro Live
- TODO broker sandbox/paper integration test
- TODO synthetic duplicate ACK/fill/reject injection
- TODO partial-fill/cancel race injection
- TODO out-of-order broker message injection
- TODO delayed ACK and delayed cancel injection
- TODO dropped message / reconnect recovery test
- TODO clock-drift injection
- TODO stale/corrupt feed injection
- TODO spread shock and price-gap injection
- TODO broker position mismatch injection
- TODO kill-switch drill
- TODO restart/reconciliation drill
- TODO sustained event-rate load test
- TODO latency-tail stress test

## 18. Promotion gates

Research -> Shadow requires formal evidence verdict, immutable version, clean TEST_READY evidence, and no unresolved critical research/data defects.

Shadow -> Micro Live additionally requires production feed/broker integration, durable idempotency, order state machine, full reconciliation, clock health, software and external emergency kill path, restart recovery, injected-failure tests, and measured latency/execution quality.

Micro Live -> Live additionally requires sufficient forward sample, live/shadow equivalence within preregistered limits, no unresolved critical incidents, stable realized execution costs, stable risk controls, operational runbook, and explicit approved release/config hash.

## Immediate sequence
1. Finish EXP-0001 real evidence run without modifying locked alpha.
2. In parallel build broker-neutral execution safety primitives only.
3. Select/confirm actual broker/FCM route before adapter implementation.
4. Implement durable order journal + idempotency + reconciliation.
5. Implement latency percentile telemetry and clock-health monitor.
6. Implement kill/watchdog and injected-failure test harness.
7. Integrate paper/shadow broker path.
8. Run prolonged shadow twin.
9. Only then consider Micro Live.
