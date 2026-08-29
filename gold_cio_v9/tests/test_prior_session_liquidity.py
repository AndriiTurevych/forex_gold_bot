from datetime import date

import pytest

from gold_cio_v9.data.prior_session_liquidity import build_prior_session_liquidity


def _row(ticker, volume, session="2025-05-30"):
    return {"ticker": ticker, "session_end_date": session, "volume": volume}


def test_builds_snapshot_and_treats_explicit_empty_response_as_zero():
    snap = build_prior_session_liquidity(
        {"GCM5": [], "GCQ5": [_row("GCQ5", 1200)]},
        expected_contracts=["GCM5", "GCQ5"],
        session_date=date(2025, 5, 30),
    )
    assert snap.session_date == date(2025, 5, 30)
    assert snap.volume_by_contract == {"GCM5": 0.0, "GCQ5": 1200.0}


def test_multiple_rows_are_summed_deterministically():
    snap = build_prior_session_liquidity(
        {"GCQ5": [_row("GCQ5", 10), _row("GCQ5", 15.5)]},
        expected_contracts=["GCQ5"],
        session_date=date(2025, 5, 30),
    )
    assert snap.volume_by_contract["GCQ5"] == 25.5


def test_missing_response_fails_closed():
    with pytest.raises(ValueError, match="missing completed liquidity response"):
        build_prior_session_liquidity(
            {"GCQ5": [_row("GCQ5", 1)]},
            expected_contracts=["GCM5", "GCQ5"],
            session_date=date(2025, 5, 30),
        )


def test_wrong_session_or_ticker_fails_closed():
    with pytest.raises(ValueError, match="session date mismatch"):
        build_prior_session_liquidity(
            {"GCQ5": [_row("GCQ5", 1, session="2025-06-02")]},
            expected_contracts=["GCQ5"],
            session_date=date(2025, 5, 30),
        )
    with pytest.raises(ValueError, match="ticker mismatch"):
        build_prior_session_liquidity(
            {"GCQ5": [_row("GCM5", 1)]},
            expected_contracts=["GCQ5"],
            session_date=date(2025, 5, 30),
        )


def test_invalid_volume_and_unexpected_response_fail_closed():
    with pytest.raises(ValueError, match="invalid session volume"):
        build_prior_session_liquidity(
            {"GCQ5": [_row("GCQ5", -1)]},
            expected_contracts=["GCQ5"],
            session_date=date(2025, 5, 30),
        )
    with pytest.raises(ValueError, match="unexpected liquidity responses"):
        build_prior_session_liquidity(
            {"GCQ5": [_row("GCQ5", 1)], "GCZ5": []},
            expected_contracts=["GCQ5"],
            session_date=date(2025, 5, 30),
        )
