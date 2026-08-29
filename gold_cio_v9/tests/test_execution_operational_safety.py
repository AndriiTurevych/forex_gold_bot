import pytest

from gold_cio_v9.execution.operational_safety import (
    IdempotencyRegistry,
    OperationalLimits,
    OperationalState,
    deterministic_order_key,
    evaluate_operational_safety,
)
from gold_cio_v9.execution.order_state import OrderState, OrderStatus, transition


def _state(**overrides):
    base = dict(
        kill_switch_active=False,
        broker_connected=True,
        feed_connected=True,
        clock_drift_ms=10.0,
        position_mismatch_contracts=0,
        unknown_order_state=False,
        duplicate_order_detected=False,
        recent_reject_rate=0.0,
        observed_slippage_points=0.10,
    )
    base.update(overrides)
    return OperationalState(**base)


def test_operational_gate_approves_clean_state():
    assert evaluate_operational_safety(_state()).approved


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("kill_switch_active", True, "KILL_SWITCH_ACTIVE"),
        ("broker_connected", False, "BROKER_DISCONNECTED"),
        ("feed_connected", False, "FEED_DISCONNECTED"),
        ("clock_drift_ms", 101.0, "CLOCK_DRIFT_VETO"),
        ("unknown_order_state", True, "UNKNOWN_ORDER_STATE"),
        ("duplicate_order_detected", True, "DUPLICATE_ORDER_VETO"),
        ("position_mismatch_contracts", 1, "POSITION_RECONCILIATION_VETO"),
        ("recent_reject_rate", 0.06, "REJECT_RATE_VETO"),
        ("observed_slippage_points", 0.51, "SLIPPAGE_VETO"),
    ],
)
def test_operational_gate_fails_closed(field, value, reason):
    decision = evaluate_operational_safety(_state(**{field: value}), OperationalLimits())
    assert not decision.approved
    assert decision.reason == reason


def test_deterministic_order_key_and_registry_block_duplicate():
    key1 = deterministic_order_key(
        signal_id="sig-1", strategy_version="EXP-0001", account="A", instrument="GC", side="BUY"
    )
    key2 = deterministic_order_key(
        signal_id="sig-1", strategy_version="EXP-0001", account="A", instrument="GC", side="BUY"
    )
    assert key1 == key2
    registry = IdempotencyRegistry()
    assert registry.register_once(key1)
    assert not registry.register_once(key2)


def test_order_state_handles_partial_fill_cancel_race():
    order = OrderState("cid-1", requested_qty=3)
    order = transition(order, OrderStatus.SUBMITTED)
    order = transition(order, OrderStatus.ACKNOWLEDGED)
    order = transition(order, OrderStatus.PARTIALLY_FILLED, filled_qty=1)
    order = transition(order, OrderStatus.CANCEL_PENDING)
    order = transition(order, OrderStatus.PARTIALLY_FILLED, filled_qty=2)
    order = transition(order, OrderStatus.CANCELED, filled_qty=2)
    assert order.status is OrderStatus.CANCELED
    assert order.filled_qty == 2


def test_order_state_unknown_can_recover_by_reconciliation():
    order = OrderState("cid-2", requested_qty=1)
    order = transition(order, OrderStatus.SUBMITTED)
    order = transition(order, OrderStatus.UNKNOWN)
    order = transition(order, OrderStatus.FILLED, filled_qty=1)
    order = transition(order, OrderStatus.RECONCILED)
    assert order.status is OrderStatus.RECONCILED


def test_illegal_order_transition_fails_closed():
    order = OrderState("cid-3", requested_qty=1)
    with pytest.raises(ValueError):
        transition(order, OrderStatus.FILLED, filled_qty=1)
