from types import SimpleNamespace

from gold_cio_v9.live.account_state import collect_account_state


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_OUT_BY = 3

    def __init__(self):
        self.account = SimpleNamespace(
            equity=1000.0, balance=995.0, trade_mode=0,
            trade_allowed=True, trade_expert=True,
        )
        self.positions = [SimpleNamespace(magic=56002026), SimpleNamespace(magic=123)]
        self.deals = [
            SimpleNamespace(magic=56002026, entry=1, time_msc=1, profit=-5.0, commission=0, swap=0, fee=0),
            SimpleNamespace(magic=56002026, entry=1, time_msc=2, profit=-3.0, commission=0, swap=0, fee=0),
        ]

    def initialize(self, *args, **kwargs): return True
    def account_info(self): return self.account
    def positions_get(self): return tuple(self.positions)
    def history_deals_get(self, start, end): return tuple(self.deals)
    def shutdown(self): pass
    def last_error(self): return (0, "OK")


def test_account_state_is_redacted_and_counts_midas_risk():
    result = collect_account_state(FakeMT5(), terminal_path=None)
    assert result["demo_account"] is True
    assert result["open_positions"] == 1
    assert result["consecutive_losses"] == 2
    assert result["daily_loss_fraction"] > 0
    assert "login" not in result
    assert result["real_orders_allowed"] is False
