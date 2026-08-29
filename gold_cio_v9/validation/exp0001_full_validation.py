"""Outcome-independent statistical reducer for the locked EXP-0001 full test.

Consumes trade-level evidence books produced under base and 1.5x stressed costs,
then applies the pre-outcome V3 partition policy. No strategy thresholds or horizon
selection are performed here; 60 minutes is the locked promotion horizon and the
other horizons are used only for diagnostics/PBO.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from math import floor, isfinite
from statistics import mean
from typing import Mapping, Sequence

from gold_cio_v9.backtest.splits import LabelInterval, purged_kfold
from gold_cio_v9.experiments.exp0001_evidence_book import EvidenceBook, EvidenceTrade
from gold_cio_v9.validation.acceptance import ValidationMetrics
from gold_cio_v9.validation.metrics import (
    removal_top_trades_expectancy,
    top_fraction_pnl_share,
    trade_metrics,
)
from gold_cio_v9.validation.statistics import deflated_sharpe_test, pbo_from_rank_paths

PRIMARY_HORIZON = 60
HORIZONS = (5, 15, 30, 60)
PURGED_FOLDS = 5
EMBARGO_MINUTES = 60
TOP_FRACTION = 0.05
TOP_SHARE_MAX = 0.50
REGIME_MIN_N = 30


@dataclass(frozen=True)
class ChronologicalPartition:
    development_ids: tuple[str, ...]
    oos_ids: tuple[str, ...]
    holdout_ids: tuple[str, ...]


@dataclass(frozen=True)
class FullValidationDiagnostics:
    total_primary_candidates: int
    resolved_oos: int
    ambiguous_oos: int
    resolved_holdout: int
    walk_forward_test_expectancies: tuple[float, ...]
    pbo: float
    dsr_p_value: float
    top_positive_pnl_share: float
    expectancy_after_top_removal: float
    catastrophic_regimes: tuple[str, ...]
    low_n_negative_regimes: tuple[str, ...]


@dataclass(frozen=True)
class FullValidationBuild:
    partition: ChronologicalPartition
    metrics: ValidationMetrics
    diagnostics: FullValidationDiagnostics


def _primary(book: EvidenceBook) -> tuple[EvidenceTrade, ...]:
    if tuple(book.horizons_minutes) != HORIZONS:
        raise ValueError("evidence book horizons do not match locked EXP-0001 policy")
    return book.trades_for_horizon(PRIMARY_HORIZON)


def chronological_partition(book: EvidenceBook) -> ChronologicalPartition:
    """Freeze 60/20/20 membership from candidate timestamps, not outcomes."""
    trades = _primary(book)
    if len(trades) < 5:
        raise ValueError("insufficient primary candidates for chronological partition")
    ids = [t.candidate_id for t in trades]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate primary candidate IDs")
    n = len(ids)
    dev_end = floor(n * 0.60)
    oos_end = floor(n * 0.80)
    if dev_end <= 0 or oos_end <= dev_end or oos_end >= n:
        raise ValueError("chronological partition would contain an empty block")
    return ChronologicalPartition(tuple(ids[:dev_end]), tuple(ids[dev_end:oos_end]), tuple(ids[oos_end:]))


def _map(book: EvidenceBook, horizon: int) -> dict[str, EvidenceTrade]:
    rows = book.trades_for_horizon(horizon)
    out: dict[str, EvidenceTrade] = {}
    for t in rows:
        if t.candidate_id in out:
            raise ValueError("duplicate candidate ID within horizon")
        out[t.candidate_id] = t
    return out


def _finite_pnls(mapping: Mapping[str, EvidenceTrade], ids: Sequence[str]) -> list[float]:
    values: list[float] = []
    for cid in ids:
        t = mapping.get(cid)
        if t is None:
            raise ValueError(f"candidate {cid} missing from evidence horizon")
        if t.resolved:
            if not isfinite(t.net_pnl_price):
                raise ValueError("resolved trade has non-finite PnL")
            values.append(float(t.net_pnl_price))
    return values


def _timestamp_minute(t: EvidenceTrade) -> int:
    dt = t.signal_time.astimezone(timezone.utc)
    return int(dt.timestamp() // 60)


def _purged_rank_paths(book: EvidenceBook, pre_holdout_ids: Sequence[str]) -> tuple[list[int], list[int], bool]:
    maps = {h: _map(book, h) for h in HORIZONS}
    primary_map = maps[PRIMARY_HORIZON]
    intervals = [
        LabelInterval(i, _timestamp_minute(primary_map[cid]), _timestamp_minute(primary_map[cid]) + PRIMARY_HORIZON)
        for i, cid in enumerate(pre_holdout_ids)
    ]
    if len(intervals) < PURGED_FOLDS:
        return [], [], False
    splits = purged_kfold(intervals, PURGED_FOLDS, embargo=EMBARGO_MINUTES)
    is_ranks: list[int] = []
    oos_ranks: list[int] = []
    effective_ok = True

    for split in splits:
        train_ids = [pre_holdout_ids[i] for i in split.train]
        test_ids = [pre_holdout_ids[i] for i in split.test]
        is_exp: dict[int, float] = {}
        oos_exp: dict[int, float] = {}
        for h in HORIZONS:
            train = _finite_pnls(maps[h], train_ids)
            test = _finite_pnls(maps[h], test_ids)
            if not train or not test:
                effective_ok = False
                break
            is_exp[h] = mean(train)
            oos_exp[h] = mean(test)
        if not effective_ok:
            break
        is_order = sorted(HORIZONS, key=lambda h: (-is_exp[h], h))
        oos_order = sorted(HORIZONS, key=lambda h: (-oos_exp[h], h))
        is_rank = {h: i + 1 for i, h in enumerate(is_order)}
        oos_rank = {h: i + 1 for i, h in enumerate(oos_order)}
        for h in HORIZONS:
            is_ranks.append(is_rank[h])
            oos_ranks.append(oos_rank[h])
    return is_ranks, oos_ranks, effective_ok


def _walk_forward_expectancies(primary: Mapping[str, EvidenceTrade], pre_holdout_ids: Sequence[str]) -> tuple[float, ...]:
    n = len(pre_holdout_ids)
    min_train = max(1, floor(n * 0.50))
    test_size = max(1, floor(n * 0.10))
    step = test_size
    values: list[float] = []
    test_start = min_train
    while test_start + test_size <= n:
        ids = pre_holdout_ids[test_start : test_start + test_size]
        pnl = _finite_pnls(primary, ids)
        if not pnl:
            values.append(float("-inf"))
        else:
            values.append(mean(pnl))
        test_start += step
    return tuple(values)


def _regime_checks(
    primary: Mapping[str, EvidenceTrade],
    oos_ids: Sequence[str],
    regime_labels: Mapping[str, Sequence[str]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    by_regime: dict[str, list[float]] = {}
    for cid in oos_ids:
        trade = primary[cid]
        if cid not in regime_labels:
            raise ValueError(f"missing preregistered regime labels for {cid}")
        labels = tuple(regime_labels[cid])
        if not labels:
            raise ValueError(f"empty preregistered regime labels for {cid}")
        if not trade.resolved:
            continue
        for label in labels:
            by_regime.setdefault(str(label), []).append(float(trade.net_pnl_price))

    catastrophic: list[str] = []
    low_n_negative: list[str] = []
    for label, pnl in sorted(by_regime.items()):
        exp = mean(pnl)
        if exp <= 0 and len(pnl) >= REGIME_MIN_N:
            catastrophic.append(label)
        elif exp <= 0:
            low_n_negative.append(label)
    return tuple(catastrophic), tuple(low_n_negative)


def build_validation_metrics(
    *,
    base_book: EvidenceBook,
    stress_1_5x_book: EvidenceBook,
    trial_count: int,
    regime_labels: Mapping[str, Sequence[str]],
    data_integrity_ok: bool,
    post_result_parameter_edits: bool = False,
) -> FullValidationBuild:
    """Build the exact ValidationMetrics consumed by the locked acceptance gate."""
    if trial_count < 1:
        raise ValueError("trial_count must be >= 1")
    partition = chronological_partition(base_book)
    primary = _map(base_book, PRIMARY_HORIZON)
    stress = _map(stress_1_5x_book, PRIMARY_HORIZON)
    if set(primary) != set(stress):
        raise ValueError("base/stress candidate universes differ")
    for cid in primary:
        if primary[cid].signal_time != stress[cid].signal_time:
            raise ValueError("base/stress candidate timestamps differ")

    oos_all = [primary[cid] for cid in partition.oos_ids]
    oos = _finite_pnls(primary, partition.oos_ids)
    holdout = _finite_pnls(primary, partition.holdout_ids)
    stressed_oos = _finite_pnls(stress, partition.oos_ids)
    if not oos or not holdout or not stressed_oos:
        raise ValueError("OOS/holdout/stress partitions require finite resolved trades")

    oos_metrics = trade_metrics(oos)
    holdout_metrics = trade_metrics(holdout)
    stress_metrics = trade_metrics(stressed_oos)
    ambiguous = sum(1 for t in oos_all if not t.resolved)
    ambiguity_rate = ambiguous / len(oos_all) if oos_all else 1.0

    pre_holdout = partition.development_ids + partition.oos_ids
    is_rank, oos_rank, effective_ok = _purged_rank_paths(base_book, pre_holdout)
    pbo = pbo_from_rank_paths(is_rank, oos_rank) if effective_ok and is_rank else 1.0

    wf = _walk_forward_expectancies(primary, pre_holdout)
    walk_forward_stable = bool(wf) and all(isfinite(x) and x > 0 for x in wf)

    dsr = deflated_sharpe_test(oos, trials=trial_count)
    top_share = top_fraction_pnl_share(oos, TOP_FRACTION)
    top_removed = removal_top_trades_expectancy(oos, TOP_FRACTION)
    catastrophic, low_n_negative = _regime_checks(primary, partition.oos_ids, regime_labels)

    metrics = ValidationMetrics(
        oos_expectancy=oos_metrics.expectancy,
        oos_profit_factor=oos_metrics.profit_factor,
        raw_oos_setups=oos_metrics.count,
        effective_sample_ok=effective_ok,
        walk_forward_stable=walk_forward_stable,
        holdout_expectancy=holdout_metrics.expectancy,
        dsr_ok=dsr.significant,
        pbo=pbo,
        expectancy_cost_1_5x=stress_metrics.expectancy,
        top_trade_removal_ok=top_removed > 0,
        concentration_ok=top_share <= TOP_SHARE_MAX,
        catastrophic_regime=bool(catastrophic),
        data_integrity_ok=bool(data_integrity_ok),
        post_result_parameter_edits=bool(post_result_parameter_edits),
        ambiguous_oos_setups=ambiguous,
        ambiguity_rate=ambiguity_rate,
    )
    diagnostics = FullValidationDiagnostics(
        total_primary_candidates=len(primary),
        resolved_oos=oos_metrics.count,
        ambiguous_oos=ambiguous,
        resolved_holdout=holdout_metrics.count,
        walk_forward_test_expectancies=wf,
        pbo=pbo,
        dsr_p_value=dsr.p_value,
        top_positive_pnl_share=top_share,
        expectancy_after_top_removal=top_removed,
        catastrophic_regimes=catastrophic,
        low_n_negative_regimes=low_n_negative,
    )
    return FullValidationBuild(partition, metrics, diagnostics)
