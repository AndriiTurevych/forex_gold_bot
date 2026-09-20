from types import SimpleNamespace

from gold_cio_v9.live.ea_command import _command, _decision_id, publish_ea_command


def _decision(approved=True):
    return {
        "symbol": "XAUUSD",
        "decision_time": "2026-09-20T09:00:00+00:00",
        "final_action": "BUY" if approved else "ABSTAIN",
        "entry": 4300.20,
        "stop": 4298.20,
        "tp1": 4302.20,
        "tp2": 4304.20,
        "proposed_volume_lots": 0.10,
        "demo_execution_allowed": approved,
        "real_orders_allowed": False,
        "risk_gate": {"limits": {"max_spread_points": 80.0}},
    }


def test_command_abstains_when_not_approved():
    cmd = _command(_decision(False), ttl_seconds=90)
    assert cmd["action"] == "ABSTAIN"
    assert cmd["volume_lots"] == 0.0
    assert cmd["real_orders_allowed"] == 0


def test_decision_id_is_stable_and_exact_double_range():
    a = _decision_id(_decision())
    b = _decision_id(_decision())
    assert a == b
    assert 0 <= a < 2**52


class FakeMT5:
    def __init__(self, common):
        self.common = common
        self.initialized = False

    def initialize(self, *args, **kwargs):
        self.initialized = True
        return True

    def terminal_info(self):
        return SimpleNamespace(commondata_path=str(self.common))

    def shutdown(self):
        self.initialized = False

    def last_error(self):
        return (0, "OK")


def test_publish_is_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("MIDAS_EA_COMMAND_ENABLED", raising=False)
    result = publish_ea_command(FakeMT5(tmp_path), _decision(), terminal_path=None)
    assert result["published"] is False


def test_publish_writes_common_file(monkeypatch, tmp_path):
    monkeypatch.setenv("MIDAS_EA_COMMAND_ENABLED", "1")
    result = publish_ea_command(FakeMT5(tmp_path), _decision(), terminal_path=None)
    assert result["published"] is True
    target = tmp_path / "Files" / "MIDAS" / "midas_command.csv"
    assert target.exists()
    text = target.read_text(encoding="ascii")
    assert "MIDAS_V2_EA_1" in text
    assert ";BUY;" in text
