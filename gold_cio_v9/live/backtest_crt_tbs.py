"""Causal broker-M1 replay for MIDAS CRT+TBS.

This is a deterministic structural backtest. It uses historical MT5 M1 bid bars
and recorded spread points, never future bars to form a signal. It intentionally
does not reconstruct historical GPT decisions or the MT5 economic-calendar veto;
those must be validated prospectively in DEMO.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Iterable

from gold_cio_v9.live.crt_tbs import _atr, _candidate
from gold_cio_v9.live.mt5_analysis import Candle, resample_closed


@dataclass(frozen=True)
class M1ReplayBar:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    spread_points: float


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value=datetime.fromisoformat(value)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("NAIVE_REPLAY_TIMESTAMP")
    return value.astimezone(timezone.utc)


def _m1_rows(rows: Iterable[dict[str, Any]]) -> list[M1ReplayBar]:
    out=[]
    for row in rows:
        bar=M1ReplayBar(
            _utc(row["time"]),
            float(row["open"]),float(row["high"]),float(row["low"]),float(row["close"]),
            max(0.0,float(row.get("spread_points",0.0) or 0.0)),
        )
        if not all(isfinite(v) and v>0 for v in (bar.open,bar.high,bar.low,bar.close)):
            raise ValueError("INVALID_REPLAY_PRICE")
        if not bar.low<=min(bar.open,bar.close)<=max(bar.open,bar.close)<=bar.high:
            raise ValueError("INVALID_REPLAY_OHLC")
        out.append(bar)
    out.sort(key=lambda b:b.time)
    if any(a.time>=b.time for a,b in zip(out,out[1:])):
        raise ValueError("REPLAY_BARS_NOT_STRICTLY_CHRONOLOGICAL")
    return out


def _candles(m1: list[M1ReplayBar]) -> list[Candle]:
    return [Candle(b.time,b.open,b.high,b.low,b.close) for b in m1]


def _index_by_time(bars: list[Candle]) -> dict[datetime,int]:
    return {bar.time:i for i,bar in enumerate(bars)}


def _signals_for_model(
    *,
    model: str,
    refs: list[Candle],
    triggers: list[Candle],
    trigger_minutes: int,
    ref_minutes: int,
    min_rr_tp2: float,
) -> list[tuple[datetime,Any]]:
    """Generate first causal TBS candidate per stable range/side signal id."""
    if len(refs)<2 or len(triggers)<16:
        return []
    trigger_index=_index_by_time(triggers)
    seen=set()
    found=[]
    for reference in refs:
        ref_close=reference.time+timedelta(minutes=ref_minutes)
        next_ref_close=ref_close+timedelta(minutes=ref_minutes)
        for trigger in triggers:
            trigger_close=trigger.time+timedelta(minutes=trigger_minutes)
            if trigger.time<ref_close:
                continue
            # At exactly the next HTF close the reference has changed; do not
            # attribute that just-closed LTF candle to the old range.
            if trigger_close>=next_ref_close:
                break
            idx=trigger_index[trigger.time]
            history=triggers[:idx+1]
            atr=_atr(history)
            if atr is None:
                continue
            setup=_candidate(
                model=model,
                reference=reference,
                trigger=trigger,
                atr=atr,
                min_sweep_fraction=0.02,
                max_sweep_fraction=0.33,
                min_body_fraction=0.30,
                min_rr_tp2=min_rr_tp2,
            )
            if setup is None or setup.signal_id in seen:
                continue
            seen.add(setup.signal_id)
            found.append((trigger_close,setup))
    return found


def generate_signals(m1: list[M1ReplayBar], *, min_rr_tp2: float=1.80) -> list[tuple[datetime,Any]]:
    base=_candles(m1)
    m5=resample_closed(base,5)
    m15=resample_closed(base,15)
    h1=resample_closed(base,60)
    h4=resample_closed(base,240)
    signals=[]
    signals.extend(_signals_for_model(
        model="H1_M5",refs=h1,triggers=m5,trigger_minutes=5,ref_minutes=60,min_rr_tp2=min_rr_tp2
    ))
    signals.extend(_signals_for_model(
        model="H4_M15",refs=h4,triggers=m15,trigger_minutes=15,ref_minutes=240,min_rr_tp2=min_rr_tp2
    ))
    signals.sort(key=lambda row:(row[0],row[1].signal_id))
    return signals


def _simulate_one(
    bars: list[M1ReplayBar],
    start_index: int,
    setup: Any,
    *,
    point: float,
    min_rr_tp2: float,
    spread_multiplier: float,
) -> dict[str,Any] | None:
    entry_bar=bars[start_index]
    entry_spread=max(0.0,entry_bar.spread_points*point*spread_multiplier)
    direction=setup.direction
    entry=entry_bar.open+entry_spread if direction=="LONG" else entry_bar.open
    stop=float(setup.stop)
    tp1=float(setup.tp1)
    tp2=float(setup.tp2)
    risk=abs(entry-stop)
    reward=abs(tp2-entry)
    if risk<=0 or reward/risk<min_rr_tp2:
        return None
    if direction=="LONG" and not (stop<entry<tp1<tp2):
        return None
    if direction=="SHORT" and not (tp2<tp1<entry<stop):
        return None

    be_active=False
    for i in range(start_index,len(bars)):
        bar=bars[i]
        spread=max(0.0,bar.spread_points*point*spread_multiplier)
        if direction=="LONG":
            low,high=bar.low,bar.high
            if not be_active:
                # Worst-case ordering for an ambiguous bar: adverse stop first.
                if low<=stop:
                    exit_price=stop
                    reason="SL"
                    r=(exit_price-entry)/risk
                    return {"exit_index":i,"exit_time":bar.time.isoformat(),"exit_price":exit_price,"exit_reason":reason,"r_multiple":r}
                if high>=tp1:
                    # If BE and TP2 are both reachable after TP1 in the same M1,
                    # take the conservative path.
                    if low<=entry:
                        return {"exit_index":i,"exit_time":bar.time.isoformat(),"exit_price":entry,"exit_reason":"BE_AMBIGUOUS","r_multiple":0.0}
                    if high>=tp2:
                        return {"exit_index":i,"exit_time":bar.time.isoformat(),"exit_price":tp2,"exit_reason":"TP2","r_multiple":(tp2-entry)/risk}
                    be_active=True
            else:
                if low<=entry:
                    return {"exit_index":i,"exit_time":bar.time.isoformat(),"exit_price":entry,"exit_reason":"BE","r_multiple":0.0}
                if high>=tp2:
                    return {"exit_index":i,"exit_time":bar.time.isoformat(),"exit_price":tp2,"exit_reason":"TP2","r_multiple":(tp2-entry)/risk}
        else:
            # Historical MT5 OHLC is bid. A short is closed by ask, so shift the
            # replay bar by the contemporaneous recorded spread.
            low,high=bar.low+spread,bar.high+spread
            if not be_active:
                if high>=stop:
                    exit_price=stop
                    return {"exit_index":i,"exit_time":bar.time.isoformat(),"exit_price":exit_price,"exit_reason":"SL","r_multiple":(entry-exit_price)/risk}
                if low<=tp1:
                    if high>=entry:
                        return {"exit_index":i,"exit_time":bar.time.isoformat(),"exit_price":entry,"exit_reason":"BE_AMBIGUOUS","r_multiple":0.0}
                    if low<=tp2:
                        return {"exit_index":i,"exit_time":bar.time.isoformat(),"exit_price":tp2,"exit_reason":"TP2","r_multiple":(entry-tp2)/risk}
                    be_active=True
            else:
                if high>=entry:
                    return {"exit_index":i,"exit_time":bar.time.isoformat(),"exit_price":entry,"exit_reason":"BE","r_multiple":0.0}
                if low<=tp2:
                    return {"exit_index":i,"exit_time":bar.time.isoformat(),"exit_price":tp2,"exit_reason":"TP2","r_multiple":(entry-tp2)/risk}
    return None


def backtest_crt_tbs(
    rows: Iterable[dict[str,Any]],
    *,
    point: float,
    min_rr_tp2: float=1.80,
    spread_multiplier: float=1.0,
) -> dict[str,Any]:
    m1=_m1_rows(rows)
    if len(m1)<24*60*5:
        raise ValueError("AT_LEAST_FIVE_DAYS_M1_REQUIRED")
    if point<=0 or spread_multiplier<=0:
        raise ValueError("INVALID_BACKTEST_MARKET_PARAMETERS")

    time_to_index={bar.time:i for i,bar in enumerate(m1)}
    signals=generate_signals(m1,min_rr_tp2=min_rr_tp2)
    trades=[]
    skipped_overlap=0
    skipped_execution=0
    busy_until=-1

    for signal_time,setup in signals:
        idx=time_to_index.get(signal_time)
        if idx is None:
            # A gap immediately after the trigger makes entry unknowable.
            skipped_execution+=1
            continue
        if idx<=busy_until:
            skipped_overlap+=1
            continue
        outcome=_simulate_one(
            m1,idx,setup,point=point,min_rr_tp2=min_rr_tp2,spread_multiplier=spread_multiplier
        )
        if outcome is None:
            skipped_execution+=1
            continue

        entry_bar=m1[idx]
        entry_spread=entry_bar.spread_points*point*spread_multiplier
        entry=entry_bar.open+entry_spread if setup.direction=="LONG" else entry_bar.open
        risk=abs(entry-float(setup.stop))
        row={
            "signal_id":setup.signal_id,
            "model":setup.model,
            "direction":setup.direction,
            "range_time":setup.range_time,
            "trigger_time":setup.trigger_time,
            "signal_time":signal_time.isoformat(),
            "entry_time":entry_bar.time.isoformat(),
            "entry":round(entry,8),
            "stop":float(setup.stop),
            "tp1":float(setup.tp1),
            "tp2":float(setup.tp2),
            "entry_spread_points":entry_bar.spread_points,
            "risk_price":round(risk,8),
            **{k:(round(v,8) if isinstance(v,float) else v) for k,v in outcome.items() if k!="exit_index"},
        }
        trades.append(row)
        busy_until=int(outcome["exit_index"])

    return {
        "schema":"midas-crt-tbs-broker-backtest-v1",
        "bars":len(m1),
        "start_time":m1[0].time.isoformat(),
        "end_time":m1[-1].time.isoformat(),
        "candidate_signals":len(signals),
        "resolved_trades":len(trades),
        "skipped_overlap":skipped_overlap,
        "skipped_execution":skipped_execution,
        "spread_multiplier":spread_multiplier,
        "min_rr_tp2":min_rr_tp2,
        "trades":trades,
        "limitations":[
            "STRUCTURAL_BASELINE_ONLY",
            "HISTORICAL_GPT_GATE_NOT_RECONSTRUCTED",
            "HISTORICAL_MT5_ECONOMIC_CALENDAR_VETO_NOT_RECONSTRUCTED",
            "M1_INTRABAR_AMBIGUITY_RESOLVED_CONSERVATIVELY",
        ],
        "real_orders_allowed":False,
    }


def metrics(trades: list[dict[str,Any]], *, cost_stress_r: float=0.0) -> dict[str,Any]:
    values=[float(t["r_multiple"])-cost_stress_r for t in trades]
    if not values:
        return {"count":0,"mean_r":None,"profit_factor":None,"win_rate":None,"be_rate":None}
    wins=[v for v in values if v>1e-12]
    losses=[v for v in values if v<-1e-12]
    bes=[v for v in values if abs(v)<=1e-12]
    positive=sum(wins)
    negative=-sum(losses)
    return {
        "count":len(values),
        "mean_r":sum(values)/len(values),
        "median_r":sorted(values)[len(values)//2],
        "profit_factor":positive/negative if negative>0 else None,
        "win_rate":len(wins)/len(values),
        "loss_rate":len(losses)/len(values),
        "be_rate":len(bes)/len(values),
        "cost_stress_r":cost_stress_r,
    }
