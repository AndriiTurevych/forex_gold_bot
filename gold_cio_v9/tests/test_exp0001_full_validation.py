from datetime import datetime, timedelta, timezone

import pytest

from gold_cio_v9.experiments.exp0001_evidence_book import EvidenceBook, EvidenceBookCell, EvidenceTrade
from gold_cio_v9.validation.exp0001_full_validation import _fold_pbo, build_validation_metrics, chronological_partition


def _book(n=80, *, stress=False, ambiguous_ids=()):
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    cells = []
    for h in (5, 15, 30, 60):
        trades = []
        for i in range(n):
            resolved = i not in set(ambiguous_ids)
            pnl = (1.0 + (i % 5) * 0.1) * (0.6 if stress else 1.0)
            trades.append(EvidenceTrade(
                contract="GCG5", horizon_minutes=h, candidate_id=f"c{i:03d}",
                signal_time=t0 + timedelta(minutes=i * 120), direction="LONG",
                first_touch="TARGET" if resolved else "AMBIGUOUS",
                bars_to_first_touch=1,
                net_pnl_price=pnl if resolved else float("nan"), resolved=resolved,
            ))
        cells.append(EvidenceBookCell(
            contract="GCG5", horizon_minutes=h, status="OK",
            context_points=100, stream_events=90, replay_setups=n,
            trades=tuple(trades), data_snapshot_hash="d", candidate_snapshot_hash="c", result_hash=f"r{h}",
        ))
    return EvidenceBook("EXP-0001-BASELINE-POLICY-V1", ("GCG5",), (5, 15, 30, 60), tuple(cells))


def _regimes(n=80):
    return {f"c{i:03d}": ("NY_AM", "VOL_NORMAL") for i in range(n)}


def test_partition_is_outcome_independent_and_60_20_20():
    b = _book(80, ambiguous_ids=(10, 20, 30))
    p = chronological_partition(b)
    assert len(p.development_ids) == 48
    assert len(p.oos_ids) == 16
    assert len(p.holdout_ids) == 16
    assert p.oos_ids[0] == "c048"


def test_fold_pbo_detects_is_winner_falling_into_oos_bottom_half():
    # 5m wins IS but ranks last OOS -> this fold is overfit with probability 1.
    is_rank = {5: 1, 15: 2, 30: 3, 60: 4}
    oos_rank = {5: 4, 15: 1, 30: 2, 60: 3}
    assert _fold_pbo(is_rank, oos_rank) == 1.0


def test_fold_pbo_passes_when_is_winner_remains_top_half_oos():
    is_rank = {5: 1, 15: 2, 30: 3, 60: 4}
    oos_rank = {5: 2, 15: 1, 30: 3, 60: 4}
    assert _fold_pbo(is_rank, oos_rank) == 0.0


def test_full_metrics_positive_fixture():
    out = build_validation_metrics(
        base_book=_book(80), stress_1_5x_book=_book(80, stress=True),
        trial_count=1, regime_labels=_regimes(), data_integrity_ok=True,
    )
    m = out.metrics
    assert m.oos_expectancy > 0
    assert m.oos_profit_factor == float("inf")
    assert m.holdout_expectancy > 0
    assert m.expectancy_cost_1_5x > 0
    assert m.pbo == 0
    assert m.effective_sample_ok is True
    assert m.walk_forward_stable is True
    assert m.data_integrity_ok is True
    assert m.raw_oos_setups == 16


def test_ambiguous_oos_is_excluded_from_resolved_count_but_retained_in_rate():
    out = build_validation_metrics(
        base_book=_book(80, ambiguous_ids=(50, 55)),
        stress_1_5x_book=_book(80, stress=True, ambiguous_ids=(50, 55)),
        trial_count=1, regime_labels=_regimes(), data_integrity_ok=True,
    )
    assert out.metrics.raw_oos_setups == 14
    assert out.metrics.ambiguous_oos_setups == 2
    assert out.metrics.ambiguity_rate == pytest.approx(2 / 16)


def test_stress_candidate_universe_mismatch_fails_closed():
    stress = _book(80, stress=True)
    first = stress.cells[0]
    changed = list(first.trades)
    changed.pop()
    bad_first = EvidenceBookCell(
        first.contract, first.horizon_minutes, first.status, first.context_points,
        first.stream_events, first.replay_setups, tuple(changed), first.data_snapshot_hash,
        first.candidate_snapshot_hash, first.result_hash,
    )
    bad = EvidenceBook(stress.policy_id, stress.contracts, stress.horizons_minutes, (bad_first,) + stress.cells[1:])
    with pytest.raises(ValueError, match="candidate universes differ"):
        build_validation_metrics(
            base_book=_book(80), stress_1_5x_book=bad, trial_count=1,
            regime_labels=_regimes(), data_integrity_ok=True,
        )


def test_missing_regime_label_fails_closed():
    labels = _regimes()
    del labels["c050"]
    with pytest.raises(ValueError, match="missing preregistered regime labels"):
        build_validation_metrics(
            base_book=_book(80), stress_1_5x_book=_book(80, stress=True),
            trial_count=1, regime_labels=labels, data_integrity_ok=True,
        )
