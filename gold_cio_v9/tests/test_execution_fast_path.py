from gold_cio_v9.execution.fast_path import (
    FastPathContext,
    FastPathDecision,
    FastPathInput,
    evaluate_fast_path,
)
from gold_cio_v9.execution.latency import LatencyBudget, LatencyTrace


def _ctx(**overrides):
    base = dict(
        computed_ns=9_500_000_000,
        regime_allowed=True,
        location_allowed=True,
        macro_allowed=True,
        data_quality_ok=True,
        model_health_ok=True,
    )
    base.update(overrides)
    return FastPathContext(**base)


def _candidate(**overrides):
    base = dict(
        signal_id="sig-1",
        trigger_ns=10_000_000_000,
        decision_ns=10_020_000_000,
        theoretical_entry=4700.0,
        current_price=4700.1,
        side="BUY",
        alpha_qualified=True,
        meta_take=True,
        risk_veto=False,
        context=_ctx(),
    )
    base.update(overrides)
    return FastPathInput(**base)


def test_fast_path_takes_fresh_valid_candidate():
    result = evaluate_fast_path(_candidate(), LatencyBudget())
    assert result.decision is FastPathDecision.TAKE
    assert result.reason == "FAST_PATH_APPROVED"


def test_fast_path_stales_slow_decision():
    result = evaluate_fast_path(
        _candidate(decision_ns=10_060_000_000), LatencyBudget(trigger_to_decision_ms=50)
    )
    assert result.decision is FastPathDecision.STALE
    assert result.reason == "DECISION_LATENCY_BREACH"


def test_fast_path_stales_old_context():
    result = evaluate_fast_path(
        _candidate(context=_ctx(computed_ns=8_000_000_000)),
        LatencyBudget(max_context_age_ms=1_000),
    )
    assert result.decision is FastPathDecision.STALE
    assert result.reason == "CONTEXT_TOO_OLD"


def test_fast_path_vetoes_bad_data_before_alpha():
    result = evaluate_fast_path(
        _candidate(context=_ctx(data_quality_ok=False), alpha_qualified=False), LatencyBudget()
    )
    assert result.decision is FastPathDecision.VETO
    assert result.reason == "DATA_QUALITY_VETO"


def test_fast_path_vetoes_risk():
    result = evaluate_fast_path(_candidate(risk_veto=True), LatencyBudget())
    assert result.decision is FastPathDecision.VETO
    assert result.reason == "RISK_VETO"


def test_fast_path_skips_disallowed_regime():
    result = evaluate_fast_path(
        _candidate(context=_ctx(regime_allowed=False)), LatencyBudget()
    )
    assert result.decision is FastPathDecision.SKIP
    assert result.reason == "REGIME_NOT_ALLOWED"


def test_buy_entry_degradation_is_adverse_price_increase():
    result = evaluate_fast_path(
        _candidate(current_price=4700.31),
        LatencyBudget(max_entry_degradation_points=0.30),
    )
    assert result.decision is FastPathDecision.STALE
    assert result.reason == "ENTRY_DEGRADED"


def test_sell_entry_degradation_is_adverse_price_decrease():
    result = evaluate_fast_path(
        _candidate(side="SELL", current_price=4699.69),
        LatencyBudget(max_entry_degradation_points=0.30),
    )
    assert result.decision is FastPathDecision.STALE
    assert result.reason == "ENTRY_DEGRADED"


def test_latency_trace_tracks_total_and_stage_budgets():
    trace = LatencyTrace(signal_id="sig", signal_created_ns=1_000_000_000)
    trace.add_stage("decision", 1_000_000_000, 1_020_000_000)
    trace.add_stage("order_submit", 1_020_000_000, 1_030_000_000)
    trace.mark_order_sent(1_030_000_000)
    assert trace.signal_to_order_ms == 30.0
    assert trace.within_budget(LatencyBudget())


def test_latency_trace_flags_total_budget_breach():
    trace = LatencyTrace(signal_id="sig", signal_created_ns=1_000_000_000)
    trace.mark_order_sent(1_150_000_000)
    assert not trace.within_budget(LatencyBudget(total_signal_to_order_ms=100))
