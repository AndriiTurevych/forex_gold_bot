"""LONA/Backtrader challenger for MIDAS v10 Lean.

This is an independent single-feed M15 approximation used only for falsification.
The production decision layer remains gold_cio_v9.strategies.midas_v10_lean.
"""
import backtrader as bt


class MidasV10LeanLona(bt.Strategy):
    params = (
        ("lookback", 8),
        ("atr_period", 14),
        ("fast_ema", 16),
        ("slow_ema", 64),
        ("displacement_atr", 1.2),
        ("stop_buffer_atr", 0.10),
        ("risk_fraction", 0.0025),
        ("reward_risk", 2.0),
        ("max_trades_day", 2),
        ("session_start_utc", 6),
        ("session_end_utc", 20),
        ("setup_expiry", 8),
    )

    def __init__(self):
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.fast = bt.indicators.EMA(self.data.close, period=self.p.fast_ema)
        self.slow = bt.indicators.EMA(self.data.close, period=self.p.slow_ema)
        self.pending_direction = 0
        self.pending_low = 0.0
        self.pending_high = 0.0
        self.pending_stop = 0.0
        self.pending_age = 0
        self.stop_price = None
        self.target_price = None
        self.current_day = None
        self.trades_today = 0

    def _reset_day(self):
        day = self.data.datetime.date(0)
        if day != self.current_day:
            self.current_day = day
            self.trades_today = 0

    def _session_open(self):
        hour = self.data.datetime.datetime(0).hour
        return self.p.session_start_utc <= hour < self.p.session_end_utc

    def _prior_low(self):
        return min(float(self.data.low[-i]) for i in range(1, self.p.lookback + 1))

    def _prior_high(self):
        return max(float(self.data.high[-i]) for i in range(1, self.p.lookback + 1))

    def _clear_pending(self):
        self.pending_direction = 0
        self.pending_age = 0

    def _enter(self, direction):
        entry = float(self.data.close[0])
        stop = self.pending_stop
        distance = abs(entry - stop)
        if distance <= 0:
            self._clear_pending()
            return
        cash_risk = float(self.broker.getvalue()) * self.p.risk_fraction
        leverage_cap = float(self.broker.getcash()) * 5.0 / max(entry, 1e-12)
        size = min(cash_risk / distance, leverage_cap)
        if size <= 0:
            self._clear_pending()
            return
        if direction > 0:
            self.buy(size=size)
            self.stop_price = stop
            self.target_price = entry + self.p.reward_risk * distance
        else:
            self.sell(size=size)
            self.stop_price = stop
            self.target_price = entry - self.p.reward_risk * distance
        self.trades_today += 1
        self._clear_pending()

    def next(self):
        minimum = max(self.p.slow_ema, self.p.atr_period, self.p.lookback) + 3
        if len(self) < minimum:
            return
        self._reset_day()
        close = float(self.data.close[0])

        if self.position:
            if self.position.size > 0 and (close <= self.stop_price or close >= self.target_price):
                self.close()
            elif self.position.size < 0 and (close >= self.stop_price or close <= self.target_price):
                self.close()
            return

        if not self._session_open() or self.trades_today >= self.p.max_trades_day:
            self._clear_pending()
            return

        if self.pending_direction:
            self.pending_age += 1
            if self.pending_age > self.p.setup_expiry:
                self._clear_pending()
                return
            overlaps = (
                float(self.data.high[0]) >= self.pending_low
                and float(self.data.low[0]) <= self.pending_high
            )
            regime_ok = (
                self.pending_direction > 0 and self.fast[0] > self.slow[0]
            ) or (
                self.pending_direction < 0 and self.fast[0] < self.slow[0]
            )
            if overlaps and regime_ok:
                self._enter(self.pending_direction)
            return

        atr = float(self.atr[0])
        if atr <= 0:
            return
        prior_low = self._prior_low()
        prior_high = self._prior_high()
        body_atr = abs(close - float(self.data.open[0])) / atr

        bullish_sweep = float(self.data.low[0]) < prior_low and close > prior_low
        bearish_sweep = float(self.data.high[0]) > prior_high and close < prior_high
        bullish_displacement = close > float(self.data.open[0]) and body_atr >= self.p.displacement_atr
        bearish_displacement = close < float(self.data.open[0]) and body_atr >= self.p.displacement_atr
        bullish_fvg = float(self.data.low[0]) > float(self.data.high[-2])
        bearish_fvg = float(self.data.high[0]) < float(self.data.low[-2])

        if bullish_sweep and bullish_displacement and bullish_fvg and self.fast[0] > self.slow[0]:
            self.pending_direction = 1
            self.pending_low = float(self.data.high[-2])
            self.pending_high = float(self.data.low[0])
            self.pending_stop = float(self.data.low[0]) - self.p.stop_buffer_atr * atr
            self.pending_age = 0
        elif bearish_sweep and bearish_displacement and bearish_fvg and self.fast[0] < self.slow[0]:
            self.pending_direction = -1
            self.pending_low = float(self.data.high[0])
            self.pending_high = float(self.data.low[-2])
            self.pending_stop = float(self.data.high[0]) + self.p.stop_buffer_atr * atr
            self.pending_age = 0
