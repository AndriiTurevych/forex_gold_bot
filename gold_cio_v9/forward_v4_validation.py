"""Fixed-calendar, nonbinding EXP-0004 evaluation; no interim return readout."""
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from gold_cio_v9.forward_v4 import utc, verified_rows, ROUND_TRIP_COST, next_minute

POLICY_PATH = Path(__file__).parent / "experiments/EXP-0004-PROTOCOL.json"


def policy():
    return json.loads(POLICY_PATH.read_text())


def policy_hash():
    return sha256(POLICY_PATH.read_bytes()).hexdigest()


def boundaries(start):
    p = policy()
    start = utc(start)
    return start + timedelta(days=p["holdout_start_day"]), start + timedelta(days=p["duration_days"])


def admission_reason(start, now):
    start, now = utc(start), utc(now)
    split, end = boundaries(start)
    embargo = timedelta(minutes=policy()["boundary_embargo_minutes"])
    if now < start:
        return "BEFORE_REGISTERED_START"
    if now >= end - embargo:
        return "REGISTERED_COLLECTION_CLOSED"
    if split - embargo <= now < split:
        return "HOLDOUT_BOUNDARY_EMBARGO"
    return None


def checkpoint(ledger, engine_commit):
    rows = verified_rows(ledger)
    if not rows:
        raise ValueError("EMPTY_LEDGER")
    return {"experiment_id": "EXP-0004", "sequence": len(rows),
            "tip_hash": rows[-1]["record_hash"], "engine_commit": engine_commit,
            "protocol_hash": policy_hash(), "ledger_sha256": sha256(ledger.path.read_bytes()).hexdigest()}


def verify_checkpoint(ledger, expected, engine_commit):
    # expected must come from a separately pinned Git commit or immutable run
    # artifact identity, never from the untrusted ledger being restored.
    if checkpoint(ledger, engine_commit) != expected:
        raise ValueError("CHECKPOINT_MISMATCH_OR_TRUNCATION")


def partition_statistics(observations, start, days):
    p = policy()
    sums, counts = np.zeros(days), np.zeros(days)
    values = []
    for when, gross in observations:
        day = (utc(when) - utc(start)).days
        if not 0 <= day < days or not np.isfinite(gross):
            raise ValueError("INVALID_OBSERVATION")
        value = gross - ROUND_TRIP_COST
        sums[day] += value
        counts[day] += 1
        values.append(value)
    if len(values) < p["min_complete_observations_per_partition"] or np.count_nonzero(counts) < p["min_active_days_per_partition"]:
        return {"enough_data": False, "count": len(values), "active_days": int(np.count_nonzero(counts))}
    # Circular moving calendar blocks retain empty days and within-block
    # clustering. This is approximate dependent-data inference, not a guarantee.
    rng = np.random.default_rng(p["bootstrap_seed"])
    block = p["bootstrap_block_days"]
    means = []
    for _ in range(p["bootstrap_replicates"]):
        offsets = rng.integers(0, days, size=(days + block - 1) // block)
        indices = ((offsets[:, None] + np.arange(block)) % days).reshape(-1)[:days]
        denominator = counts[indices].sum()
        if denominator:
            means.append(sums[indices].sum() / denominator)
    if len(means) < .99 * p["bootstrap_replicates"]:
        return {"enough_data": False, "reason": "SPARSE_BOOTSTRAP"}
    positive = sum(max(v, 0) for v in values)
    negative = -sum(min(v, 0) for v in values)
    pf_pass = positive >= p["min_profit_factor_per_partition"] * negative and positive > 0
    mean = float(np.mean(values))
    lower = float(np.quantile(means, p["one_sided_lower_quantile"]))
    stress_mean = mean - ROUND_TRIP_COST * (p["cost_stress_multiplier"] - 1)
    return {"enough_data": True, "count": len(values), "active_days": int(np.count_nonzero(counts)),
            "mean_net_usd_per_ounce": mean, "lower_bound": lower,
            "profit_factor": positive / negative if negative else None,
            "zero_losses": negative == 0, "stress_mean": stress_mean,
            "passed": lower > 0 and mean >= p["minimum_mean_net_usd_per_ounce"] and stress_mean > 0 and pf_pass}


def evaluate(ledger, *, now, expected_checkpoint, engine_commit):
    verify_checkpoint(ledger, expected_checkpoint, engine_commit)
    rows = verified_rows(ledger)
    genesis = rows[0]
    if (genesis["event_type"] != "GENESIS" or genesis["payload"].get("scope") != "PROSPECTIVE_NONBINDING"
            or genesis["payload"].get("protocol_hash") != policy_hash()
            or genesis["payload"].get("engine_commit") != engine_commit):
        raise ValueError("UNREGISTERED_OR_ENGINEERING_LEDGER")
    start = utc(genesis["payload"]["start_time"])
    split, end = boundaries(start)
    base = {"experiment_id": "EXP-0004", "formal_verdict_allowed": False, "real_orders_allowed": False,
            "scope": "NONBINDING_PAPER_RETURN_RESEARCH", "protocol_hash": policy_hash(), "end_time": end.isoformat()}
    if utc(now) <= end + timedelta(hours=25):
        return {**base, "verdict": "PENDING", "reason": "FIXED_END_NOT_REACHED"}
    decisions, outcomes, fills, missing = {}, {}, {}, set()
    for row in rows[1:]:
        p, kind = row["payload"], row["event_type"]
        if kind == "DECISION" and p["action"] in {"BUY", "SELL"}:
            sid = p["signal_id"]
            if sid in decisions or p["engine_commit"] != engine_commit or admission_reason(start, p["decision_time"]):
                raise ValueError("INVALID_REGISTERED_DECISION")
            decisions[sid] = p
        elif kind == "SIMULATED_FILL":
            if p["signal_id"] in fills:
                raise ValueError("DUPLICATE_FILL")
            fills[p["signal_id"]] = p
        elif kind in {"FILL_MISSING", "OUTCOME_MISSING"}:
            if kind == "FILL_MISSING" or p["horizon_minutes"] == 60:
                missing.add(p["signal_id"])
        elif kind == "OUTCOME" and p["horizon_minutes"] == 60:
            if p["signal_id"] in outcomes:
                raise ValueError("DUPLICATE_PRIMARY_OUTCOME")
            outcomes[p["signal_id"]] = p
    if set(outcomes) - set(decisions) or missing - set(decisions):
        raise ValueError("ORPHAN_OUTCOME")
    if missing or set(decisions) != set(outcomes):
        return {**base, "verdict": "INSUFFICIENT_DATA", "reason": "MISSING_OR_UNSETTLED_PRIMARY"}
    development, holdout = [], []
    for sid, p in decisions.items():
        when = utc(p["decision_time"])
        fill, outcome = fills.get(sid), outcomes[sid]
        if fill is None:
            raise ValueError("OUTCOME_WITHOUT_FILL")
        target = next_minute(when)
        maturity = target + timedelta(minutes=60)
        if (utc(fill["fill_time"]) != target or utc(p["fill_target_time"]) != target
                or utc(outcome["exit_time"]) != maturity
                or utc(outcome["exit_bar_start"]) != maturity - timedelta(minutes=1)
                or utc(fill["observed_at"]) < target + timedelta(minutes=1)
                or utc(fill["observed_at"]) > target + timedelta(hours=24, minutes=1)
                or utc(outcome["observed_at"]) < maturity
                or utc(outcome["observed_at"]) > maturity + timedelta(hours=24)
                or fill["contract"] != p["contract"] or outcome["contract"] != p["contract"]):
            raise ValueError("INVALID_FILL_OR_OUTCOME_TIMING")
        gross = (1 if p["action"] == "BUY" else -1) * (outcome["exit_price"] - fill["entry_price"])
        if not np.isfinite(gross) or abs(gross - outcome["gross_price"]) > 1e-8:
            raise ValueError("OUTCOME_ARITHMETIC_MISMATCH")
        (development if when < split else holdout).append((when, gross))
    statistics = {"development": partition_statistics(development, start, 90),
                  "holdout": partition_statistics(holdout, split, 90)}
    if not all(s["enough_data"] for s in statistics.values()):
        return {**base, "verdict": "INSUFFICIENT_DATA", "statistics": statistics}
    passed = all(s["passed"] for s in statistics.values())
    return {**base, "verdict": "ACCEPT_NONBINDING" if passed else "REJECT", "statistics": statistics,
            "interpretation": "Paper-return hypothesis only; executable profitability is not established."}
