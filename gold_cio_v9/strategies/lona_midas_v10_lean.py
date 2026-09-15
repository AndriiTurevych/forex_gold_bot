"""LONA/Backtrader single-feed challenger for MIDAS v10 Lean.

Research/falsification only. It cannot authorize live execution.
"""
import backtrader as bt


class MidasV10LeanLona(bt.Strategy):
    params = (
        ("lookback", 8), ("atr_period", 14), ("fast_ema", 16), ("slow_ema", 64),
        ("displacement_atr", 1.2), ("stop_buffer_atr", 0.10),
        ("risk_fraction", 0.0025), ("reward_risk", 2.0),
        ("max_trades_day", 2), ("session_start_utc", 6), ("session_end_utc", 20),
        ("setup_expiry", 8),
    )

    def __init__(self):
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.fast = bt.indicators.EMA(self.data.close, period=self.p.fast_ema)
        self.slow = bt.indicators.EMA(self.data.close, period=self.p.slow_ema)
        self.sweep_direction = 0
        self.sweep_extreme = 0.0
        self.sweep_age = 0
        self.pending_direction = 0
        self.pending_low = self.pending_high = self.pending_stop = 0.0
        self.pending_age = 0
        self.stop_price = self.target_price = None
        self.current_day = None
        self.trades_today = 0

    def _reset_day(self):
        day = self.data.datetime.date(0)
        if day != self.current_day:
            self.current_day, self.trades_today = day, 0

    def _session_open(self):
        hour = self.data.datetime.datetime(0).hour
        return self.p.session_start_utc <= hour < self.p.session_end_utc

    def _clear_setup(self):
        self.sweep_direction = self.sweep_age = 0
        self.pending_direction = self.pending_age = 0

    def _enter(self):
        entry, stop = float(self.data.close[0]), self.pending_stop
        distance = abs(entry - stop)
        valid_stop = (self.pending_direction > 0 and stop < entry) or (self.pending_direction < 0 and stop > entry)
        if distance <= 0 or not valid_stop:
            self._clear_setup()
            return
        cash_risk = float(self.broker.getvalue()) * self.p.risk_fraction
        leverage_cap = float(self.broker.getcash()) * 5.0 / max(entry, 1e-12)
        size = min(cash_risk / distance, leverage_cap)
        if size <= 0:
            self._clear_setup()
            return
        if self.pending_direction > 0:
            self.buy(size=size)
            self.target_price = entry + self.p.reward_risk * distance
        else:
            self.sell(size=size)
            self.target_price = entry - self.p.reward_risk * distance
        self.stop_price = stop
        self.trades_today += 1
        self._clear_setup()

    def next(self):
        if len(self) < max(self.p.slow_ema, self.p.atr_period, self.p.lookback) + 3:
            return
        self._reset_day()
        close = float(self.data.close[0])

        if self.position:
            long_exit = self.position.size > 0 and (close <= self.stop_price or close >= self.target_price)
            short_exit = self.position.size < 0 and (close >= self.stop_price or close <= self.target_price)
            if long_exit or short_exit:
                self.close()
            return

        if not self._session_open() or self.trades_today >= self.p.max_trades_day:
            self._clear_setup()
            return

        if self.pending_direction:
            self.pending_age += 1
            if self.pending_age > self.p.setup_expiry:
                self._clear_setup()
                return
            overlaps = float(self.data.high[0]) >= self.pending_low and float(self.data.low[0]) <= self.pending_high
            regime_ok = (self.pending_direction > 0 and self.fast[0] > self.slow[0]) or (
                self.pending_direction < 0 and self.fast[0] < self.slow[0])
            if overlaps and regime_ok:
                self._enter()
            return

        atr = float(self.atr[0])
        if atr <= 0:
            return
        body_atr = abs(close - float(self.data.open[0])) / atr
        bull_displacement = close > float(self.data.open[0]) and body_atr >= self.p.displacement_atr
        bear_displacement = close < float(self.data.open[0]) and body_atr >= self.p.displacement_atr
        bull_fvg = float(self.data.low[0]) > float(self.data.high[-2])
        bear_fvg = float(self.data.high[0]) < float(self.data.low[-2])

        if self.sweep_direction:
            self.sweep_age += 1
            if self.sweep_age > self.p.setup_expiry:
                self._clear_setup()
                return
            if self.sweep_direction > 0 and bull_displacement and bull_fvg and self.fast[0] > self.slow[0]:
                self.pending_direction = 1
                self.pending_low, self.pending_high = float(self.data.high[-2]), float(self.data.low[0])
                self.pending_stop = self.sweep_extreme - self.p.stop_buffer_atr * atr
                self.pending_age = 0
                self.sweep_direction = 0
            elif self.sweep_direction < 0 and bear_displacement and bear_fvg and self.fast[0] < self.slow[0]:
                self.pending_direction = -1
                self.pending_low, self.pending_high = float(self.data.high[0]), float(self.data.low[-2])
                self.pending_stop = self.sweep_extreme + self.p.stop_buffer_atr * atr
                self.pending_age = 0
                self.sweep_direction = 0
            return

        prior_low = min(float(self.data.low[-i]) for i in range(1, self.p.lookback + 1))
        prior_high = max(float(self.data.high[-i]) for i in range(1, self.p.lookback + 1))
        bull_sweep = float(self.data.low[0]) < prior_low and close > prior_low
        bear_sweep = float(self.data.high[0]) > prior_high and close < prior_high
        if bull_sweep != bear_sweep:
            self.sweep_direction = 1 if bull_sweep else -1
            self.sweep_extreme = float(self.data.low[0]) if bull_sweep else float(self.data.high[0])
            self.sweep_age = 0
