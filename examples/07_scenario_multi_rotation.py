import math
from collections import defaultdict, deque

import pandas as pd

from example_utils import QuietLogger, flatten_position, target_position_value
from minbt import Broker, Exchange, Strategy


SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT")


def build_sample_data() -> pd.DataFrame:
    """构造不同阶段强弱切换的多标的行情。"""
    rows = []
    prices = {
        "BTCUSDT": 100.0,
        "ETHUSDT": 100.0,
        "SOLUSDT": 100.0,
        "BNBUSDT": 100.0,
    }
    for step in range(72):
        dt = f"2026-03-{step + 1:02d}"
        for symbol in SYMBOLS:
            if symbol == "BTCUSDT":
                drift = 0.20 + 0.28 * math.sin(step / 11)
            elif symbol == "ETHUSDT":
                drift = 0.10 + (0.55 if 18 <= step < 45 else -0.05) + 0.10 * math.sin(step / 4)
            elif symbol == "SOLUSDT":
                drift = -0.08 + (0.75 if step >= 42 else 0.0) + 0.18 * math.sin(step / 5)
            else:
                drift = 0.08 + 0.08 * math.sin(step / 3)
            prices[symbol] = max(1.0, prices[symbol] + drift)
            rows.append(
                {
                    "dt": dt,
                    "symbol": symbol,
                    "close": round(prices[symbol], 4),
                }
            )
    return pd.DataFrame(rows)


class CrossSectionRotationStrategy(Strategy):
    """多标的横截面动量：定期持有动量最强的两个标的。"""

    def __init__(
        self,
        strategy_id: str,
        broker: Broker,
        lookback: int = 12,
        rebalance_interval: int = 6,
        top_n: int = 2,
        gross_fraction: float = 0.90,
        leverage: float = 1.5,
    ):
        super().__init__(strategy_id=strategy_id, broker=broker)
        self.lookback = lookback
        self.rebalance_interval = rebalance_interval
        self.top_n = top_n
        self.gross_fraction = gross_fraction
        self.leverage = leverage

    def on_init(self):
        self.price_history = defaultdict(lambda: deque(maxlen=self.lookback + 1))
        self.bar_count = 0
        self.rebalance_count = 0
        self.last_selection = []

    def on_bars(self, dt, bars):
        for symbol, row in bars.items():
            self.price_history[symbol].append(float(row["close"]))

        self.bar_count += 1
        enough_history = all(len(self.price_history[symbol]) > self.lookback for symbol in SYMBOLS)
        if not enough_history or self.bar_count % self.rebalance_interval != 0:
            return

        momentum = {}
        for symbol in SYMBOLS:
            prices = list(self.price_history[symbol])
            momentum[symbol] = prices[-1] / prices[0] - 1.0

        selected = sorted(momentum, key=momentum.get, reverse=True)[: self.top_n]
        self.last_selection = selected
        equity = self.broker.get_equity()
        target_value = equity * self.gross_fraction / len(selected)
        changed = False

        for symbol in SYMBOLS:
            price = float(bars[symbol]["close"])
            if symbol in selected:
                changed = target_position_value(
                    self.broker,
                    symbol,
                    target_value,
                    price,
                    leverage=self.leverage,
                ) or changed
            else:
                changed = flatten_position(self.broker, symbol, price) or changed

        if changed:
            self.rebalance_count += 1

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_cash={self.broker.get_cash():.2f}")
        print(f"final_positions={self.broker.get_position_sizes()}")
        print(f"last_selection={self.last_selection}")
        print(f"rebalance_count={self.rebalance_count}")


def run_strategy(quiet: bool = True):
    quiet_logger = QuietLogger() if quiet else None
    exchange = Exchange(logger=quiet_logger)
    exchange.set_bars(build_sample_data(), date_key="dt")

    broker = Broker(initial_cash=100_000, fee_rate=0.0005, leverage=1.5, logger=quiet_logger)
    strategy = CrossSectionRotationStrategy(strategy_id="scenario_multi_rotation", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()
    return strategy, broker


if __name__ == "__main__":
    run_strategy()
