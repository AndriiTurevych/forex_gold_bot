from pathlib import Path


EA = Path("mt5/MQL5/Experts/MIDAS/MIDAS_V2_DemoEA.mq5")


def _source():
    return EA.read_text(encoding="utf-8")


def test_ea_is_hard_blocked_to_demo_accounts():
    source = _source()
    assert "ACCOUNT_TRADE_MODE_DEMO" in source
    assert "REAL_OR_NONDEMO_ACCOUNT_BLOCKED" in source
    assert "real_orders_allowed!=0" in source


def test_ea_requires_explicit_enable_and_trade_permissions():
    source = _source()
    assert "InpEnableDemoExecution" in source
    assert "TERMINAL_TRADE_ALLOWED" in source
    assert "MQL_TRADE_ALLOWED" in source
    assert "ACCOUNT_TRADE_EXPERT" in source


def test_ea_has_duplicate_and_existing_position_guards():
    source = _source()
    assert "DUPLICATE_DECISION" in source
    assert "MIDAS_POSITION_ALREADY_OPEN" in source
    assert "SYMBOL_POSITION_ALREADY_EXISTS" in source


def test_ea_manages_breakeven_and_checks_server_retcode():
    source = _source()
    assert "STOP_MOVED_TO_BREAKEVEN" in source
    assert "trade.ResultRetcode()" in source
    assert "TRADE_RETCODE_DONE" in source


def test_ea_renders_cockpit_and_saves_native_template():
    source = _source()
    assert "UpdateCockpit" in source
    assert "ChartSaveTemplate" in source
    assert "MIDAS_V2_XAUUSD" in source
    assert "MIDAS 2.0 | " in source
    assert "GPT GATE" in source
    assert "RISK GATE" in source


def test_ea_reads_v2_dashboard_command_schema():
    source = _source()
    assert 'MIDAS_V2_EA_2' in source
    assert 'setup_model' in source
    assert 'confidence' in source
    assert 'spread_points' in source


def test_ea_has_high_impact_usd_calendar_veto():
    source = _source()
    assert "CalendarValueHistory" in source
    assert "CALENDAR_IMPORTANCE_HIGH" in source
    assert "HIGH_IMPACT_USD_EVENT_LOCK" in source
    assert "ECONOMIC_CALENDAR_UNAVAILABLE" in source


def test_ea_journals_open_and_close_events_for_empirical_validation():
    source = _source()
    assert "MIDAS_V2_EA_EVENT_1" in source
    assert 'AppendEvent("OPENED"' in source
    assert 'AppendEvent("CLOSE_DEAL"' in source
    assert "OnTradeTransaction" in source
    assert "OrderCalcProfit" in source
