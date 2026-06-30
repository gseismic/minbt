import math
from collections import deque

import pandas as pd

from example_utils import target_position_value
from minbt import Broker, Exchange, Strategy


SYMBOL = "BTCUSDT"


def build_sample_data() -> pd.DataFrame:
    """构造带有盘整、突破、回撤和二次趋势的单标的行情。"""
    rows = []
    close = 100.0
    for step in range(96):
        if step < 24:
            drift = 0.04 * math.sin(step / 2)
        elif step < 54:
            drift = 0.55 + 0.12 * math.sin(step / 3)
        elif step < 72:
            drift = -0.45 + 0.18 * math.sin(step / 2)
        else:
            drift = 0.34 + 0.08 * math.sin(step / 4)
        close = max(1.0, close + drift)
        daily_range = 0.7 + 0.25 * abs(math.sin(step / 5))
        rows.append(
            {
                "dt": f"2026-02-{step + 1:02d}",
                "symbol": SYMBOL,
                "open": round(close - drift, 4),
                "high": round(close + daily_range, 4),
                "low": round(close - daily_range, 4),
                "close": round(close, 4),
            }
        )
    return pd.DataFrame(rows)


class BreakoutWithStopStrategy(Strategy):
    """单标的趋势突破：突破入场，波动止损，目标名义金额调仓。"""

    def __init__(
        self,
        strategy_id: str,
        broker: Broker,
        lookback: int = 18,
        atr_window: int = 10,
        target_fraction: float = 0.75,
        leverage: float = 2.0,
    ):
        super().__init__(strategy_id=strategy_id, broker=broker)
        self.lookback = lookback
        self.atr_window = atr_window
        self.target_fraction = target_fraction
        self.leverage = leverage

    def on_init(self):
        self.closes = deque(maxlen=self.lookback + 1)
        self.true_ranges = deque(maxlen=self.atr_window)
        self.prev_close = None
        self.entry_price = None
        self.highest_close = None
        self.trade_count = 0
        self.stop_count = 0

    def on_bars(self, dt, bars):
        row = bars[SYMBOL]
        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])
        if self.prev_close is not None:
            true_range = max(high - low, abs(high - self.prev_close), abs(low - self.prev_close))
            self.true_ranges.append(true_range)

        if len(self.closes) >= self.lookback and len(self.true_ranges) >= self.atr_window:
            atr = sum(self.true_ranges) / len(self.true_ranges)
            previous_closes = list(self.closes)
            current_size = self.broker.get_position_size(SYMBOL)

            if current_size > 0:
                self.highest_close = max(self.highest_close or close, close)
                stop_price = max(self.entry_price - 2.0 * atr, self.highest_close - 3.0 * atr)
                if close < stop_price:
                    if target_position_value(self.broker, SYMBOL, 0.0, close, leverage=self.leverage):
                        self.stop_count += 1
                        self.trade_count += 1
                    self.entry_price = None
                    self.highest_close = None
            else:
                breakout = close > max(previous_closes[-self.lookback:])
                volatility_ok = atr / close < 0.04
                if breakout and volatility_ok:
                    target_value = self.broker.get_equity() * self.target_fraction
                    if target_position_value(self.broker, SYMBOL, target_value, close, leverage=self.leverage):
                        self.entry_price = close
                        self.highest_close = close
                        self.trade_count += 1

        self.closes.append(close)
        self.prev_close = close

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_cash={self.broker.get_cash():.2f}")
        print(f"final_position={self.broker.get_position_size(SYMBOL):.6f}")
        print(f"trade_count={self.trade_count}")
        print(f"stop_count={self.stop_count}")


def run_strategy():
    exchange = Exchange()
    exchange.set_bars(build_sample_data(), date_key="dt")

    broker = Broker(initial_cash=100_000, fee_rate=0.0005, leverage=2.0)
    strategy = BreakoutWithStopStrategy(strategy_id="scenario_single_breakout", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()
    return strategy, broker


if __name__ == "__main__":
    run_strategy()
