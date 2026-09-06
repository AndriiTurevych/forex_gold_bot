from datetime import date
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")


PATH = Path("gold_cio_v9/experiments/EXP-0002.yaml")


def _spec():
    return yaml.safe_load(PATH.read_text(encoding="utf-8"))


def test_exp0002_is_locked_before_any_outcome():
    spec = _spec()
    assert spec["id"] == "EXP-0002"
    assert spec["status"] == "LOCKED_BEFORE_OUTCOMES"
    assert spec["strategy_outcomes_generated"] is False
    assert spec["governance"]["post_result_parameter_rescue_allowed"] is False


def test_exp0002_evidence_does_not_overlap_exp0001():
    independence = _spec()["independence"]
    assert date.fromisoformat(independence["evidence_end"]) < date(2025, 4, 2)
    assert independence["evidence_overlap_with_exp0001"] == "forbidden"


def test_exp0002_order_flow_rules_are_fully_locked():
    flow = _spec()["order_flow"]
    assert flow["window_seconds"] == 60
    assert flow["maximum_quote_age_milliseconds"] == 2000
    assert flow["classified_volume_minimum_fraction"] == pytest.approx(0.80)
    assert flow["long_imbalance_minimum"] == pytest.approx(0.20)
    assert flow["short_imbalance_maximum"] == pytest.approx(-0.20)
    assert flow["threshold_search_allowed"] is False


def test_exp0002_requires_sample_and_untouched_holdout():
    validation = _spec()["validation"]
    assert validation["minimum_resolved_oos_primary"] == 200
    assert validation["untouched_holdout_required"] is True
    assert validation["cost_stress_multiple"] == pytest.approx(1.5)
