from types import SimpleNamespace

from gold_cio_v9.live.demo_execution import execute_demo_decision, manage_demo_position


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 2
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 2
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0

    def __init__(self, trade_mode=0):
        self.account = SimpleNamespace(trade_mode=trade_mode, trade_allowed=True, trade_expert=True)
        self.info = SimpleNamespace(point=0.01, volume_min=0.01, volume_max=10.0, filling_mode=1)
        self.tick = SimpleNamespace(bid=4300.00, ask=4300.20)
        self.positions = []
        self.requests = []

    def account_info(self):
        return self.account

    def symbol_select(self, symbol, enabled):
        return True

    def symbol_info(self, symbol):
        return self.info

    def symbol_info_tick(self, symbol):
        return self.tick

    def positions_get(self, symbol=None):
        return tuple(self.positions)

    def order_send(self, request):
        self.requests.append(request)
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=123, deal=456)


def _decision():
    return {
        "symbol": "XAUUSD",
        "decision_time": "2026-09-20T09:00:00+00:00",
        "final_action": "BUY",
        "entry": 4300.20,
        "stop": 4298.20,
        "tp1": 4302.20,
        "tp2": 4304.20,
        "proposed_volume_lots": 0.10,
        "demo_execution_allowed": True,
        "execution_allowed": False,
        "real_orders_allowed": False,
    }


def test_demo_executor_is_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("MIDAS_DEMO_EXECUTION_ENABLED", raising=False)
    result = execute_demo_decision(FakeMT5(), _decision(), state_path=tmp_path / "state.json")
    assert result["status"] == "DISABLED"
    assert result["order_sent"] is False


def test_demo_executor_blocks_real_account(monkeypatch, tmp_path):
    monkeypatch.setenv("MIDAS_DEMO_EXECUTION_ENABLED", "1")
    result = execute_demo_decision(
        FakeMT5(trade_mode=FakeMT5.ACCOUNT_TRADE_MODE_REAL),
        _decision(),
        state_path=tmp_path / "state.json",
    )
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "REAL_OR_NONDEMO_ACCOUNT_BLOCKED"


def test_demo_executor_sends_one_demo_order_and_deduplicates(monkeypatch, tmp_path):
    monkeypatch.setenv("MIDAS_DEMO_EXECUTION_ENABLED", "1")
    mt5 = FakeMT5()
    state = tmp_path / "state.json"
    first = execute_demo_decision(mt5, _decision(), state_path=state)
    second = execute_demo_decision(mt5, _decision(), state_path=state)
    assert first["status"] == "OK"
    assert first["order_sent"] is True
    assert second["status"] == "SKIPPED"
    assert second["reason"] == "DUPLICATE_DECISION"
    assert len(mt5.requests) == 1


def test_position_manager_moves_stop_to_breakeven_after_tp1(monkeypatch, tmp_path):
    monkeypatch.setenv("MIDAS_DEMO_EXECUTION_ENABLED", "1")
    mt5 = FakeMT5()
    state = tmp_path / "state.json"
    opened = execute_demo_decision(mt5, _decision(), state_path=state)
    assert opened["order_sent"] is True

    mt5.positions = [SimpleNamespace(ticket=999, magic=56002026)]
    mt5.tick = SimpleNamespace(bid=4302.30, ask=4302.50)
    managed = manage_demo_position(mt5, state_path=state)
    assert managed["position_managed"] is True
    assert mt5.requests[-1]["action"] == mt5.TRADE_ACTION_SLTP
    assert mt5.requests[-1]["sl"] == opened["entry"]
