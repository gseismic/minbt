import math
from collections import deque

import pandas as pd

from example_utils import target_position_value
from minbt import Broker, Exchange, Strategy


BASE_SYMBOL = "BTCUSDT"
PAIR_SYMBOL = "ETHUSDT"
SYMBOLS = (BASE_SYMBOL, PAIR_SYMBOL)


def build_sample_data() -> pd.DataFrame:
    """构造两个长期相关、短期价差周期偏离的标的。"""
    rows = []
    base_price = 100.0
    for step in range(90):
        base_price += 0.18 + 0.10 * math.sin(step / 12)
        spread = 0.055 * math.sin(step / 5) + 0.018 * math.sin(step / 2)
        pair_price = base_price * (1.0 + spread)
        dt = f"2026-04-{step + 1:02d}"
        rows.append({"dt": dt, "symbol": BASE_SYMBOL, "close": round(base_price, 4)})
        rows.append({"dt": dt, "symbol": PAIR_SYMBOL, "close": round(pair_price, 4)})
    return pd.DataFrame(rows)


class PairMeanReversionStrategy(Strategy):
    """配对均值回归：价差过宽时做空强腿、做多弱腿。"""

    def __init__(
        self,
        strategy_id: str,
        broker: Broker,
        spread_window: int = 20,
        entry_z: float = 1.25,
        exit_z: float = 0.25,
        leg_fraction: float = 0.35,
        leverage: float = 2.0,
    ):
        super().__init__(strategy_id=strategy_id, broker=broker)
        self.spread_window = spread_window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.leg_fraction = leg_fraction
        self.leverage = leverage

    def on_init(self):
        self.spreads = deque(maxlen=self.spread_window)
        self.state = "flat"
        self.entry_count = 0
        self.exit_count = 0
        self.last_z = 0.0

    def on_bars(self, dt, bars):
        base_price = float(bars[BASE_SYMBOL]["close"])
        pair_price = float(bars[PAIR_SYMBOL]["close"])
        spread = math.log(pair_price / base_price)

        if len(self.spreads) >= self.spread_window:
            values = list(self.spreads)
            mean = sum(values) / len(values)
            variance = sum((value - mean) ** 2 for value in values) / len(values)
            std = math.sqrt(variance)
            self.last_z = 0.0 if std == 0 else (spread - mean) / std
            self._trade_by_z_score(self.last_z, base_price, pair_price)

        self.spreads.append(spread)

    def _trade_by_z_score(self, z_score: float, base_price: float, pair_price: float):
        equity = self.broker.get_equity()
        leg_value = equity * self.leg_fraction

        if self.state == "flat":
            if z_score > self.entry_z:
                # pair rich: short pair, long base
                self._set_pair(base_value=leg_value, pair_value=-leg_value, base_price=base_price, pair_price=pair_price)
                self.state = "short_pair"
                self.entry_count += 1
            elif z_score < -self.entry_z:
                # pair cheap: long pair, short base
                self._set_pair(base_value=-leg_value, pair_value=leg_value, base_price=base_price, pair_price=pair_price)
                self.state = "long_pair"
                self.entry_count += 1
        elif abs(z_score) < self.exit_z:
            self._set_pair(base_value=0.0, pair_value=0.0, base_price=base_price, pair_price=pair_price)
            self.state = "flat"
            self.exit_count += 1

    def _set_pair(self, base_value: float, pair_value: float, base_price: float, pair_price: float):
        target_position_value(
            self.broker,
            BASE_SYMBOL,
            base_value,
            base_price,
            leverage=self.leverage,
        )
        target_position_value(
            self.broker,
            PAIR_SYMBOL,
            pair_value,
            pair_price,
            leverage=self.leverage,
        )

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_cash={self.broker.get_cash():.2f}")
        print(f"final_positions={self.broker.get_position_sizes()}")
        print(f"state={self.state}")
        print(f"entry_count={self.entry_count}")
        print(f"exit_count={self.exit_count}")
        print(f"last_z={self.last_z:.4f}")


def run_strategy():
    exchange = Exchange()
    exchange.set_bars(build_sample_data(), date_key="dt")

    broker = Broker(initial_cash=100_000, fee_rate=0.0005, leverage=2.0)
    strategy = PairMeanReversionStrategy(strategy_id="scenario_pairs_mean_reversion", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()
    return strategy, broker


if __name__ == "__main__":
    run_strategy()
