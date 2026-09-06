import inspect

from scripts import build_exp0002_structural_windows as structural


def test_structural_window_builder_is_explicitly_outcome_free():
    source = inspect.getsource(structural)
    assert "run_backtest(" not in source
    assert "label_long(" not in source
    assert "label_short(" not in source
    assert '"strategy_outcomes_generated": False' in source
    assert '"tick_flow_applied": False' in source
