import math

import pytest

from gold_cio_v9.risk.position_sizing import SizingInputs, size_position


def _base(**overrides):
    data = dict(
        equity=100_000.0,
        risk_fraction=0.0025,
        entry=4500.0,
        stop=4490.0,
        point_value=100.0,
    )
    data.update(overrides)
    return SizingInputs(**data)


def test_position_sizing_rejects_non_finite_inputs():
    fields = [
        "equity",
        "risk_fraction",
        "entry",
        "stop",
        "point_value",
        "volatility_scale",
        "correlation_scale",
        "drawdown_scale",
        "kelly_fraction",
        "kelly_cap",
        "max_risk_fraction",
    ]
    for field in fields:
        with pytest.raises(ValueError):
            size_position(_base(**{field: math.nan}))


def test_position_sizing_rejects_negative_risk_fraction():
    with pytest.raises(ValueError):
        size_position(_base(risk_fraction=-0.001))


def test_position_sizing_rejects_invalid_kelly_controls():
    with pytest.raises(ValueError):
        size_position(_base(kelly_fraction=-0.1))
    with pytest.raises(ValueError):
        size_position(_base(kelly_cap=0.0))
    with pytest.raises(ValueError):
        size_position(_base(kelly_cap=1.01))


def test_position_sizing_respects_hard_risk_cap():
    decision = size_position(_base(risk_fraction=0.01, max_risk_fraction=0.0025))
    assert decision.effective_risk_fraction == pytest.approx(0.0025)
    assert decision.cash_risk == pytest.approx(250.0)
    assert decision.units == pytest.approx(0.25)


def test_fractional_kelly_can_only_reduce_risk():
    decision = size_position(
        _base(risk_fraction=0.0025, kelly_fraction=0.004, kelly_cap=0.25)
    )
    assert decision.effective_risk_fraction == pytest.approx(0.001)
    assert decision.effective_risk_fraction <= 0.0025
