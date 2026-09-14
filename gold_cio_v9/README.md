# Gold CIO v9

Evidence-first XAUUSD / COMEX Gold research and shadow-trading stack.

## Governing rule

AI may propose. Evidence may promote. Deterministic Risk may veto. Nothing overrides Risk.

## Pipeline

Raw Data -> Point-in-Time Feature Store -> ICT Event Engine -> Candidate Generator -> Label/Cost Engine -> Validation -> Challenger Tournament -> Shadow Trading -> Micro Live.

## Phase 1

First preregistered alpha family: Liquidity Sweep Reversal.

HTF location + external/session liquidity sweep + displacement + MSS + FVG/IFVG retest -> opposing liquidity.

The initial implementation must compare this family against simple non-ICT baselines and must include realistic transaction costs, purged/embargo validation, walk-forward testing, DSR/PBO and an untouched final holdout.

## MIDAS v10 Lean

The locked candidate composes H1/H4 agreement with the causal sequence liquidity
sweep -> displacement/MSS -> FVG/IFVG -> retest on M15. It trades only in the
06:00-20:00 UTC London/New York window, risks at most 0.25% per trade, locks at
0.5% daily loss and permits at most two entries per day.

Run a shadow decision:

```bash
python scripts/run_midas_v10_shadow.py --input gold_cio_v9/config/midas_v10_example.json
```

The evaluator always emits `execution_allowed=false`. Live promotion requires a
separate, passing OOS evidence bundle; a successful smoke test is not alpha.
