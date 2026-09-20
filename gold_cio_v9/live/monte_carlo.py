"""Empirical block-bootstrap Monte Carlo for resolved MIDAS R-multiples."""
from __future__ import annotations

import numpy as np
from typing import Iterable, Any


def monte_carlo_r(
    r_values: Iterable[float],
    *,
    risk_fraction: float = 0.0025,
    paths: int = 20000,
    horizon_trades: int = 500,
    block_size: int = 5,
    seed: int = 20260920,
) -> dict[str, Any]:
    values=np.asarray(list(r_values),dtype=float)
    if values.size < 2 or not np.isfinite(values).all():
        raise ValueError("VALID_R_MULTIPLES_REQUIRED")
    if not 0 < risk_fraction <= 0.02:
        raise ValueError("RISK_FRACTION_OUT_OF_RANGE")
    if paths < 1000 or horizon_trades < 20 or block_size < 1:
        raise ValueError("MONTE_CARLO_CONFIGURATION_INVALID")

    rng=np.random.default_rng(seed)
    blocks=(horizon_trades+block_size-1)//block_size
    finals=[]
    maxdds=[]
    chunk=2000
    n=len(values)

    for start in range(0,paths,chunk):
        m=min(chunk,paths-start)
        offsets=rng.integers(0,n,size=(m,blocks))
        indices=(offsets[:,:,None]+np.arange(block_size)[None,None,:])%n
        sampled=values[indices.reshape(m,-1)[:,:horizon_trades]]
        factors=1.0+risk_fraction*sampled
        # A trade outcome that mathematically destroys the account is treated as ruin.
        ruined=(factors<=0).any(axis=1)
        factors=np.maximum(factors,1e-12)
        equity=np.cumprod(factors,axis=1)
        peaks=np.maximum.accumulate(equity,axis=1)
        dd=1.0-equity/peaks
        final=equity[:,-1]
        final[ruined]=0.0
        finals.append(final)
        maxdds.append(dd.max(axis=1))

    finals=np.concatenate(finals)
    maxdds=np.concatenate(maxdds)
    positive=values[values>0].sum()
    negative=-values[values<0].sum()
    pf=float(positive/negative) if negative>0 else None

    return {
        "schema":"midas-empirical-monte-carlo-v1",
        "sample_size":int(values.size),
        "mean_r":float(values.mean()),
        "median_r":float(np.median(values)),
        "profit_factor_r":pf,
        "risk_fraction":risk_fraction,
        "paths":paths,
        "horizon_trades":horizon_trades,
        "block_size":block_size,
        "median_final_return":float(np.median(finals)-1.0),
        "p05_final_return":float(np.quantile(finals,0.05)-1.0),
        "p95_final_return":float(np.quantile(finals,0.95)-1.0),
        "probability_finish_below_start":float(np.mean(finals<1.0)),
        "median_max_drawdown":float(np.median(maxdds)),
        "p95_max_drawdown":float(np.quantile(maxdds,0.95)),
        "p99_max_drawdown":float(np.quantile(maxdds,0.99)),
        "probability_drawdown_10pct":float(np.mean(maxdds>=0.10)),
        "probability_drawdown_20pct":float(np.mean(maxdds>=0.20)),
        "real_orders_allowed":False,
    }


def validation_gate(mc: dict[str, Any], *, minimum_sample: int = 200) -> dict[str, Any]:
    reasons=[]
    if int(mc["sample_size"]) < minimum_sample:
        reasons.append("MINIMUM_SAMPLE_NOT_REACHED")
    if float(mc["mean_r"]) <= 0:
        reasons.append("EXPECTANCY_NOT_POSITIVE")
    pf=mc.get("profit_factor_r")
    if pf is None or float(pf) < 1.30:
        reasons.append("PROFIT_FACTOR_BELOW_1_30")
    if float(mc["p05_final_return"]) <= 0:
        reasons.append("MONTE_CARLO_P05_NOT_POSITIVE")
    if float(mc["probability_finish_below_start"]) > 0.05:
        reasons.append("MONTE_CARLO_LOSS_PROBABILITY_ABOVE_5PCT")
    if float(mc["p95_max_drawdown"]) > 0.10:
        reasons.append("MONTE_CARLO_P95_DRAWDOWN_ABOVE_10PCT")

    return {
        "schema":"midas-demo-validation-gate-v1",
        "demo_validated":not reasons,
        "minimum_sample":minimum_sample,
        "sample_size":mc["sample_size"],
        "reasons":reasons or ["DEMO_STATISTICAL_GATE_PASSED"],
        "live_release_allowed":False,
        "real_orders_allowed":False,
    }
