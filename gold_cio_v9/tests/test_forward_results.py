import csv
from pathlib import Path
from types import SimpleNamespace

from gold_cio_v9.live.forward_results import collect_resolved_trades


class FakeMT5:
    def __init__(self, common, active=False):
        self.common = common
        self.active = active
    def initialize(self, *args, **kwargs): return True
    def terminal_info(self): return SimpleNamespace(commondata_path=str(self.common))
    def positions_get(self):
        return (SimpleNamespace(identifier=77),) if self.active else ()
    def shutdown(self): pass
    def last_error(self): return (0, "OK")


def _write_events(common: Path):
    path = common / "Files" / "MIDAS" / "midas_ea_events.csv"
    path.parent.mkdir(parents=True)
    fields = ["schema","time","event","decision_id","signal_id","symbol","action","position_id",
              "deal_ticket","volume","price","sl","tp1","tp2","risk_cash","net_pnl","real_orders_allowed"]
    rows = [
        ["MIDAS_V2_EA_EVENT_1","100","OPENED","1","CRT-1","XAUUSD","BUY","77","11","0.1","4300","4298","4302","4304","20","0","0"],
        ["MIDAS_V2_EA_EVENT_1","200","CLOSE_DEAL","0","","XAUUSD","","77","12","0.1","4304","0","0","0","0","40","0"],
    ]
    with path.open("w", encoding="ascii", newline="") as h:
        w=csv.writer(h,delimiter=";")
        w.writerow(fields); w.writerows(rows)


def test_resolved_trade_computes_r_multiple(tmp_path):
    _write_events(tmp_path)
    rows=collect_resolved_trades(FakeMT5(tmp_path),terminal_path=None)
    assert len(rows)==1
    assert rows[0]["r_multiple"]==2.0
    assert rows[0]["signal_id"]=="CRT-1"


def test_open_position_is_not_resolved(tmp_path):
    _write_events(tmp_path)
    rows=collect_resolved_trades(FakeMT5(tmp_path,active=True),terminal_path=None)
    assert rows==[]
