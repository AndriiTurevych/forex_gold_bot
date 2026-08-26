from pathlib import Path

import pytest
import yaml

from gold_cio_v9.validation.trust import reject_runtime_overrides


CONFIG_PATH = Path("gold_cio_v9/config/tester_trust_gate.yaml")


def load_config():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def test_runtime_overrides_are_disabled_by_locked_policy():
    cfg = load_config()
    assert cfg["status"] == "locked"
    assert cfg["policy"]["runtime_overrides_allowed"] is False


def test_silent_runtime_override_is_rejected():
    cfg = load_config()
    with pytest.raises(ValueError, match="RUNTIME_CONFIG_OVERRIDE_FORBIDDEN"):
        reject_runtime_overrides(
            cfg["policy"],
            {"runtime_overrides_allowed": True},
        )


def test_thresholds_are_version_controlled_in_single_config():
    cfg = load_config()
    assert cfg["purged_cv"]["folds"] == 6
    assert cfg["costs"]["stress_multiple"] == 1.5
    assert cfg["acceptance"]["profit_factor_min"] == 1.30
    assert cfg["acceptance"]["pbo_max_exclusive"] == 0.20
    assert cfg["acceptance"]["independent_oos_setups_min"] == 200
