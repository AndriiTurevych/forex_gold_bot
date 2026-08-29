from datetime import date

import pytest

from gold_cio_v9.data.causal_roll import PriorSessionLiquidity, select_causal_liquid_front
from gold_cio_v9.data.contract_chain import ContractSpec


def _spec(ticker, last_trade, settle):
    return ContractSpec(
        ticker=ticker,
        first_trade_date=date(2020, 1, 1),
        last_trade_date=last_trade,
        settlement_date=settle,
    )


def test_prior_session_liquidity_selects_actual_liquid_contract():
    specs = [
        _spec("GCM5", date(2025, 6, 26), date(2025, 6, 26)),
        _spec("GCQ5", date(2025, 8, 27), date(2025, 8, 27)),
    ]
    liquidity = PriorSessionLiquidity(
        session_date=date(2025, 5, 30),
        volume_by_contract={"GCM5": 198.0, "GCQ5": 2881.0},
    )
    assert select_causal_liquid_front(
        specs, as_of=date(2025, 6, 2), prior_liquidity=liquidity
    ) == "GCQ5"


def test_current_session_liquidity_is_rejected():
    specs = [_spec("GCQ5", date(2025, 8, 27), date(2025, 8, 27))]
    liquidity = PriorSessionLiquidity(date(2025, 6, 2), {"GCQ5": 100.0})
    with pytest.raises(ValueError, match="completed prior session"):
        select_causal_liquid_front(specs, as_of=date(2025, 6, 2), prior_liquidity=liquidity)


def test_missing_competing_contract_volume_fails_closed():
    specs = [
        _spec("GCM5", date(2025, 6, 26), date(2025, 6, 26)),
        _spec("GCQ5", date(2025, 8, 27), date(2025, 8, 27)),
    ]
    liquidity = PriorSessionLiquidity(date(2025, 5, 30), {"GCQ5": 100.0})
    with pytest.raises(ValueError, match="missing prior-session volume for GCM5"):
        select_causal_liquid_front(specs, as_of=date(2025, 6, 2), prior_liquidity=liquidity)


def test_expiry_buffer_removes_near_expiry_even_if_volume_is_higher():
    specs = [
        _spec("GCM5", date(2025, 6, 6), date(2025, 6, 6)),
        _spec("GCQ5", date(2025, 8, 27), date(2025, 8, 27)),
    ]
    liquidity = PriorSessionLiquidity(
        date(2025, 5, 30), {"GCM5": 1_000_000.0, "GCQ5": 10.0}
    )
    assert select_causal_liquid_front(
        specs, as_of=date(2025, 6, 2), prior_liquidity=liquidity, roll_buffer_days=5
    ) == "GCQ5"


def test_tie_break_is_nearest_settlement_then_ticker():
    specs = [
        _spec("GCQ5", date(2025, 8, 27), date(2025, 8, 27)),
        _spec("GCU5", date(2025, 9, 26), date(2025, 9, 26)),
    ]
    liquidity = PriorSessionLiquidity(date(2025, 5, 30), {"GCQ5": 100.0, "GCU5": 100.0})
    assert select_causal_liquid_front(
        specs, as_of=date(2025, 6, 2), prior_liquidity=liquidity
    ) == "GCQ5"


def test_negative_or_nonfinite_volume_fails_closed():
    specs = [_spec("GCQ5", date(2025, 8, 27), date(2025, 8, 27))]
    with pytest.raises(ValueError, match="invalid prior-session volume"):
        select_causal_liquid_front(
            specs,
            as_of=date(2025, 6, 2),
            prior_liquidity=PriorSessionLiquidity(date(2025, 5, 30), {"GCQ5": -1.0}),
        )
