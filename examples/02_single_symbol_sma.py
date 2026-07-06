from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collections import deque

import pandas as pd

from minbt import Broker, Exchange, Strategy


DATA_PATH = Path(__file__).with_name("data.csv")
SYMBOL = "BTCUSDT"


class SingleSymbolSmaStrategy(Strategy):
    """单标的双均线趋势跟随示例。"""

    def __init__(
        self,
        strategy_id: str,
        broker: Broker,
        short_window: int = 12,
        long_window: int = 36,
        target_qty: float = 0.002,
    ):
        super().__init__(strategy_id=strategy_id, broker=broker)
        if short_window <= 0 or long_window <= short_window:
            raise ValueError("short_window must be positive and less than long_window")
        self.short_window = short_window
        self.long_window = long_window
        self.target_qty = target_qty

    def on_init(self):
        self.prices = deque(maxlen=self.long_window)
        self.trade_count = 0

    def on_bars(self, dt, bars):
        price = bars[SYMBOL]["close"]
        self.prices.append(price)
        if len(self.prices) < self.long_window:
            return

        prices = list(self.prices)
        short_ma = sum(prices[-self.short_window:]) / self.short_window
        long_ma = sum(prices) / self.long_window
        target_size = self.target_qty if short_ma > long_ma else -self.target_qty

        order = self.broker.order_target_size(SYMBOL, target_size=target_size, price=price, leverage=2)
        if order.status == "filled":
            self.trade_count += 1

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_cash={self.broker.get_cash():.2f}")
        print(f"final_position={self.broker.get_position_size(SYMBOL):.6f}")
        print(f"trade_count={self.trade_count}")


def run_strategy():
    data = pd.read_csv(DATA_PATH)
    exchange = Exchange()
    exchange.set_bars(data[["open_time", "symbol", "close"]], date_key="open_time")

    broker = Broker(initial_cash=10_000, fee_rate=0.001, leverage=2)
    strategy = SingleSymbolSmaStrategy(strategy_id="single_symbol_sma", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()
    return strategy, broker


if __name__ == "__main__":
    run_strategy()
