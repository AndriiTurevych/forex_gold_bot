from datetime import date, datetime, time, timedelta, timezone

import pytest

from gold_cio_v9.backtest.costs import CostAssumptions, net_pnl_price, round_trip_cost_price
from gold_cio_v9.features.store import FeatureRow, PointInTimeFeatureStore
from gold_cio_v9.ict_engine.features import (
    Bar,
    dealing_range_position,
    detect_liquidity_sweep,
    displacement_atr,
)
from gold_cio_v9.ict_engine.sessions import DEFAULT_WINDOWS, SessionWindow, in_window, session_liquidity
from gold_cio_v9.ict_engine.structure import detect_structure_break
from gold_cio_v9.labels.outcomes import label_long, label_short
from gold_cio_v9.risk.gate import RiskState, evaluate


def test_bsl_sweep_requires_close_back_below_level():
    bar = Bar("t", 100.0, 102.0, 99.5, 100.5)
    sweep = detect_liquidity_sweep(bar, reference_high=101.0, reference_low=98.0)
    assert sweep is not None and sweep.side == "BSL"


def test_ict_features_fail_closed_on_nan_and_bad_ohlc():
    with pytest.raises(ValueError):
        detect_liquidity_sweep(
            Bar("t", 100.0, float("nan"), 99.0, 100.0),
            reference_high=101.0,
            reference_low=98.0,
        )
    with pytest.raises(ValueError):
        displacement_atr(Bar("t", 100.0, 99.0, 101.0, 100.0), 1.0)
    with pytest.raises(ValueError):
        dealing_range_position(float("nan"), 99.0, 101.0)
    with pytest.raises(ValueError):
        detect_liquidity_sweep(
            Bar("t", 100.0, 102.0, 99.0, 100.0),
            reference_high=98.0,
            reference_low=101.0,
        )


def test_risk_gate_vetoes_stale_data():
    state = RiskState(0.0025, 0.0, 0.0, True, False, True, False)
    decision = evaluate(state)
    assert not decision.approved
    assert decision.reason == "STALE_DATA"


def test_risk_gate_fails_closed_on_nan():
    state = RiskState(float("nan"), 0.0, 0.0, True, True, True, False)
    decision = evaluate(state)
    assert not decision.approved
    assert decision.reason == "INVALID_RISK_FRACTION"


def test_risk_gate_rejects_negative_loss_fraction():
    state = RiskState(0.001, -0.01, 0.0, True, True, True, False)
    decision = evaluate(state)
    assert not decision.approved
    assert decision.reason == "INVALID_DAILY_LOSS"


def test_cost_stress_is_applied_in_price_units():
    assumptions = CostAssumptions(0.2, 0.1, 0.05, 1.5)
    assert round_trip_cost_price(assumptions) == pytest.approx(0.6)
    assert net_pnl_price(2.0, assumptions) == pytest.approx(1.4)


def test_cost_model_rejects_non_finite_input():
    with pytest.raises(ValueError):
        CostAssumptions(float("nan"), 0.1, 0.05)
    with pytest.raises(ValueError):
        net_pnl_price(float("inf"), CostAssumptions(0.2, 0.1, 0.05))


def test_point_in_time_store_blocks_future_availability():
    t0 = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    store = PointInTimeFeatureStore()
    store.append(FeatureRow(t0, t0, {"x": 1}))
    store.append(FeatureRow(t0 + timedelta(minutes=1), t0 + timedelta(minutes=2), {"x": 2}))
    latest = store.latest(t0 + timedelta(minutes=1))
    assert latest is not None
    assert latest.values["x"] == 1


def test_point_in_time_store_rejects_naive_timestamps():
    naive = datetime(2026, 8, 26, 10, 0)
    with pytest.raises(ValueError):
        FeatureRow(naive, naive, {"x": 1})


def test_feature_row_copies_values_to_prevent_retroactive_mutation():
    t0 = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    raw = {"x": 1}
    row = FeatureRow(t0, t0, raw)
    raw["x"] = 999
    assert row.values["x"] == 1
    with pytest.raises(TypeError):
        row.values["x"] = 2


def test_latest_prefers_newest_available_revision_for_same_event():
    t0 = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    store = PointInTimeFeatureStore()
    store.append(FeatureRow(t0, t0, {"revision": 1}))
    store.append(FeatureRow(t0, t0 + timedelta(minutes=5), {"revision": 2}))
    assert store.latest(t0 + timedelta(minutes=4)).values["revision"] == 1
    assert store.latest(t0 + timedelta(minutes=5)).values["revision"] == 2


def test_overnight_session_uses_start_date_anchor_without_cross_session_leakage():
    window = SessionWindow("OVERNIGHT", time(22, 0), time(2, 0))
    rows = [
        (datetime(2026, 8, 26, 23, 0, tzinfo=timezone.utc), 101.0, 99.0),
        (datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc), 103.0, 98.0),
        (datetime(2026, 8, 27, 23, 0, tzinfo=timezone.utc), 999.0, 1.0),
    ]
    result = session_liquidity(rows, window, date(2026, 8, 26))
    assert result is not None
    assert result.high == 103.0
    assert result.low == 98.0


def test_session_timezone_handles_new_york_dst_without_fixed_utc_offset():
    window = SessionWindow("NY_AM", time(8, 30), time(11, 0), "America/New_York")
    # 09:00 New York is 13:00 UTC in July (EDT) and 14:00 UTC in January (EST).
    summer = datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc)
    winter = datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc)
    assert in_window(summer, window)
    assert in_window(winter, window)
    assert not in_window(datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc), window)


def test_default_session_windows_are_feed_timezone_independent():
    # The same instant, represented in different offsets, must classify identically.
    instant_utc = datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc)
    instant_plus_two = instant_utc.astimezone(timezone(timedelta(hours=2)))
    assert in_window(instant_utc, DEFAULT_WINDOWS["NY_AM"])
    assert in_window(instant_plus_two, DEFAULT_WINDOWS["NY_AM"])


def test_label_marks_same_bar_target_and_stop_as_ambiguous():
    label = label_long(100.0, 99.0, 102.0, [(102.5, 98.5, 100.5)])
    assert label.first_touch == "AMBIGUOUS"
    assert label.realized_r != label.realized_r  # NaN by design: ordering is unknowable from OHLC


def test_label_rejects_malformed_future_bar():
    with pytest.raises(ValueError):
        label_long(100.0, 99.0, 102.0, [(99.0, 101.0, 100.0)])


def test_long_excursions_stop_at_trade_exit():
    label = label_long(
        100.0,
        99.0,
        102.0,
        [
            (100.4, 98.8, 99.2),  # stop exits here
            (110.0, 100.0, 109.0),  # must not inflate MFE after exit
        ],
    )
    assert label.first_touch == "STOP"
    assert label.bars_to_first_touch == 1
    assert label.mfe_r == pytest.approx(0.4)
    assert label.mae_r == pytest.approx(1.2)


def test_short_excursions_stop_at_trade_exit():
    label = label_short(
        100.0,
        101.0,
        98.0,
        [
            (101.2, 99.6, 100.8),  # stop exits here
            (100.0, 90.0, 91.0),  # must not inflate MFE after exit
        ],
    )
    assert label.first_touch == "STOP"
    assert label.bars_to_first_touch == 1
    assert label.mfe_r == pytest.approx(0.4)
    assert label.mae_r == pytest.approx(1.2)


def test_structure_engine_fails_closed_on_nan_and_bad_geometry():
    with pytest.raises(ValueError):
        detect_structure_break(float("nan"), 101.0, 99.0, "BULLISH", 1.0)
    with pytest.raises(ValueError):
        detect_structure_break(100.0, 99.0, 101.0, "BULLISH", 1.0)
