"""EXP-0004 engineering candidate: causal bar-based paper execution, never orders.

Bar event_time is the START of a one-minute interval. A decision reserves the
next strictly later minute open. Settlement uses only a subsequent received
snapshot, and never substitutes another bar for a missing target interval.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import math

from gold_cio_v9.shadow.ledger import HashChainLedger

EXPERIMENT = "EXP-0004"
MINUTE = timedelta(minutes=1)
HORIZONS = (5, 15, 30, 60)
OBSERVATION_GRACE = timedelta(hours=24)
ROUND_TRIP_COST = 0.35  # USD per ounce, a research assumption, not broker evidence.


def utc(value: str | datetime) -> datetime:
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return value.astimezone(timezone.utc)


def next_minute(value: datetime) -> datetime:
    return utc(value).replace(second=0, microsecond=0) + MINUTE


def verified_rows(ledger: HashChainLedger) -> list[dict]:
    rows = ledger.read_verified()
    if any(r["payload"].get("experiment_id") != EXPERIMENT for r in rows):
        raise ValueError("EXPERIMENT_LEDGER_MISMATCH")
    return rows


def index_bars(bars, received_at: datetime) -> dict:
    received_at = utc(received_at)
    result = {}
    for bar in bars:
        start = utc(bar.event_time)
        if start.second or start.microsecond:
            raise ValueError("UNALIGNED_BAR")
        prices = (bar.open, bar.high, bar.low, bar.close)
        if (not all(math.isfinite(v) and v > 0 for v in prices)
                or not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high):
            raise ValueError("INVALID_OHLC")
        if bar.volume is None or not math.isfinite(bar.volume) or bar.volume < 0:
            raise ValueError("INVALID_VOLUME")
        key = (bar.contract, start)
        if key in result:
            raise ValueError("DUPLICATE_BAR")
        # An incomplete interval cannot contribute its future close or signal.
        if start + MINUTE <= received_at:
            result[key] = bar
    return result


def pending_contracts(ledger: HashChainLedger) -> set[str]:
    rows = verified_rows(ledger)
    terminal = {r["payload"]["signal_id"] for r in rows if r["event_type"] == "FILL_MISSING"}
    completed = {}
    for row in rows:
        if row["event_type"] in {"OUTCOME", "OUTCOME_MISSING"}:
            p = row["payload"]
            completed.setdefault(p["signal_id"], set()).add(p["horizon_minutes"])
    terminal.update(sid for sid, horizons in completed.items() if set(HORIZONS) <= horizons)
    return {r["payload"]["contract"] for r in rows
            if r["event_type"] == "DECISION" and r["payload"]["action"] in {"BUY", "SELL"}
            and r["payload"]["signal_id"] not in terminal}


def record_decision(*, ledger: HashChainLedger, candidate: dict | None,
                    bars, front_contract: str, received_at: datetime,
                    decision_at: datetime, snapshot_hash: str,
                    engine_commit: str, candidate_hash: str, commit_clock=None, veto_reason=None) -> dict:
    received_at, decision_at = utc(received_at), utc(decision_at)
    rows = verified_rows(ledger)
    if decision_at < received_at:
        raise ValueError("DECISION_BEFORE_RECEIPT")
    if not snapshot_hash or not engine_commit:
        raise ValueError("MISSING_PROVENANCE")
    index = index_bars(bars, received_at)
    front = [b for (contract, _), b in index.items() if contract == front_contract]
    latest = max((utc(b.event_time) + MINUTE for b in front), default=None)
    action, reason, signal_id, available = "ABSTAIN", "NO_NEW_CANDIDATE", None, None
    if latest is None:
        reason = "NO_FRONT_DATA"
    elif decision_at - latest > timedelta(minutes=20):
        reason = "STALE_DATA_VETO"
    elif candidate is not None:
        available = utc(candidate["structural_signal_time"]) + MINUTE
        identity = "|".join((EXPERIMENT, candidate["contract"], candidate["direction"], available.isoformat()))
        # Identity uses the event, not a rolling-window index which changes daily.
        signal_id = sha256(identity.encode()).hexdigest()
        accepted = [r["payload"] for r in rows if r["event_type"] == "DECISION"
                    and r["payload"]["action"] in {"BUY", "SELL"}]
        if candidate["contract"] != front_contract:
            reason = "WRONG_FRONT"
        elif candidate["direction"] not in {"LONG", "SHORT"}:
            reason = "INVALID_DIRECTION"
        elif available > received_at:
            reason = "FUTURE_CANDIDATE_VETO"
        elif (candidate["contract"], available - MINUTE) not in index:
            reason = "CANDIDATE_BAR_MISSING"
        elif decision_at - available > timedelta(minutes=15):
            reason = "STALE_CANDIDATE_VETO"
        elif any(p["signal_id"] == signal_id for p in accepted):
            reason = "DUPLICATE_SIGNAL"
        elif any(decision_at < utc(p["fill_target_time"]) + max(HORIZONS) * MINUTE
                 for p in accepted):
            reason = "OVERLAPPING_GC_EXPOSURE"
        else:
            action = "BUY" if candidate["direction"] == "LONG" else "SELL"
            reason = "PAPER_FILL_PENDING"
    committed_at = utc(commit_clock()) if commit_clock else decision_at
    if veto_reason:
        action, reason = "ABSTAIN", veto_reason
    if committed_at < decision_at:
        raise ValueError("CLOCK_MOVED_BACKWARD")
    if action != "ABSTAIN" and committed_at >= next_minute(decision_at):
        action, reason = "ABSTAIN", "DECISION_PERSISTENCE_WINDOW_MISSED"
    payload = {
        "experiment_id": EXPERIMENT, "engine_commit": engine_commit,
        "decision_time": decision_at.isoformat(), "received_at": received_at.isoformat(),
        "commit_checked_at": committed_at.isoformat(),
        "latest_bar_close_time": latest.isoformat() if latest else None,
        "candidate_available_at": available.isoformat() if available else None,
        "action": action, "reason": reason, "signal_id": signal_id,
        "contract": front_contract, "entry_price": None,
        "fill_target_time": next_minute(decision_at).isoformat() if action != "ABSTAIN" else None,
        "snapshot_hash": snapshot_hash, "candidate_hash": candidate_hash,
        "execution_allowed": False, "formal_verdict_allowed": False,
    }
    return ledger.append("DECISION", payload)


def settle(*, ledger: HashChainLedger, bars, received_at: datetime,
           snapshot_hash: str) -> int:
    received_at = utc(received_at)
    if not snapshot_hash:
        raise ValueError("MISSING_PROVENANCE")
    rows = verified_rows(ledger)
    index = index_bars(bars, received_at)
    fills = {r["payload"]["signal_id"]: r["payload"] for r in rows if r["event_type"] == "SIMULATED_FILL"}
    failed = {r["payload"]["signal_id"] for r in rows if r["event_type"] == "FILL_MISSING"}
    done = {(r["payload"]["signal_id"], r["payload"]["horizon_minutes"])
            for r in rows if r["event_type"] in {"OUTCOME", "OUTCOME_MISSING"}}
    count = 0

    def append(kind, payload):
        nonlocal count
        ledger.append(kind, {"experiment_id": EXPERIMENT, "observed_at": received_at.isoformat(),
                            "snapshot_hash": snapshot_hash, **payload})
        count += 1

    for row in rows:
        p = row["payload"]
        if row["event_type"] != "DECISION" or p["action"] not in {"BUY", "SELL"}:
            continue
        sid, contract = p["signal_id"], p["contract"]
        if sid in failed or received_at <= utc(p["decision_time"]):
            continue
        target = utc(p["fill_target_time"])
        if sid not in fills:
            bar = index.get((contract, target))
            deadline = target + MINUTE + OBSERVATION_GRACE
            if received_at > deadline:
                append("FILL_MISSING", {"signal_id": sid, "contract": contract,
                                       "target_time": target.isoformat(), "reason": "OBSERVATION_DEADLINE"})
                continue
            if bar is None:
                continue
            fill = {"signal_id": sid, "contract": contract, "fill_time": target.isoformat(),
                    "entry_price": bar.open, "model": "NEXT_FULL_MINUTE_OPEN_PROXY",
                    "execution_allowed": False}
            append("SIMULATED_FILL", fill)
            fills[sid] = fill
        fill = fills[sid]
        for horizon in HORIZONS:
            if (sid, horizon) in done:
                continue
            maturity = utc(fill["fill_time"]) + horizon * MINUTE
            # A 5-minute holding period ends at the close of the 4th-offset bar.
            exit_bar = index.get((contract, maturity - MINUTE))
            base = {"signal_id": sid, "contract": contract, "horizon_minutes": horizon,
                    "maturity_time": maturity.isoformat()}
            if received_at > maturity + OBSERVATION_GRACE:
                append("OUTCOME_MISSING", {**base, "reason": "OBSERVATION_DEADLINE"})
            elif exit_bar is not None and received_at >= maturity:
                sign = 1 if p["action"] == "BUY" else -1
                gross = sign * (exit_bar.close - fill["entry_price"])
                append("OUTCOME", {**base, "exit_time": maturity.isoformat(),
                                   "exit_bar_start": utc(exit_bar.event_time).isoformat(),
                                   "exit_price": exit_bar.close, "gross_price": gross,
                                   "net_price": gross - ROUND_TRIP_COST,
                                   "stress_net_price": gross - 1.5 * ROUND_TRIP_COST,
                                   "cost_price": ROUND_TRIP_COST,
                                   "formal_verdict_allowed": False})
            else:
                continue
            done.add((sid, horizon))
    return count
