from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collections import defaultdict, deque

import pandas as pd

from minbt import Broker, Exchange, Strategy


SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


class QuietLogger:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


def build_sample_data() -> pd.DataFrame:
    """构造一个多标的同时间截面行情样本。"""
    price_paths = {
        "BTCUSDT": [100, 102, 104, 103, 105, 108, 110, 109, 111, 113, 115, 116],
        "ETHUSDT": [100, 101, 100, 102, 104, 107, 111, 114, 118, 121, 119, 122],
        "SOLUSDT": [100, 99, 101, 105, 108, 106, 104, 103, 107, 112, 118, 125],
    }
    rows = []
    for step in range(12):
        dt = f"2026-01-{step + 1:02d}"
        for symbol in SYMBOLS:
            rows.append({"dt": dt, "symbol": symbol, "close": float(price_paths[symbol][step])})
    return pd.DataFrame(rows)


class CrossSectionMomentumStrategy(Strategy):
    """多标的横截面动量轮动示例。"""

    def __init__(
        self,
        strategy_id: str,
        broker: Broker,
        lookback: int = 4,
        target_qty: float = 1.0,
    ):
        super().__init__(strategy_id=strategy_id, broker=broker)
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        self.lookback = lookback
        self.target_qty = target_qty

    def on_init(self):
        self.price_history = defaultdict(lambda: deque(maxlen=self.lookback + 1))
        self.selected_symbols = []
        self.rebalance_count = 0

    def on_bar(self, dt, rows_by_symbol):
        for symbol, row in rows_by_symbol.items():
            self.price_history[symbol].append(row["close"])

        if any(len(self.price_history[symbol]) <= self.lookback for symbol in SYMBOLS):
            return

        momentum = {}
        for symbol in SYMBOLS:
            prices = list(self.price_history[symbol])
            momentum[symbol] = prices[-1] / prices[0] - 1

        selected_symbol = max(momentum, key=momentum.get)
        self.selected_symbols.append(selected_symbol)
        self._rebalance_to(selected_symbol)

    def _rebalance_to(self, selected_symbol: str):
        changed = False
        for symbol in SYMBOLS:
            target_size = self.target_qty if symbol == selected_symbol else 0
            current_size = self.broker.get_position_size(symbol)
            order_qty = target_size - current_size
            if order_qty != 0:
                self.broker.submit_market_order(symbol, qty=order_qty)
                changed = True
        if changed:
            self.rebalance_count += 1

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_cash={self.broker.get_cash():.2f}")
        print(f"final_positions={self.broker.get_position_sizes()}")
        print(f"last_selected={self.selected_symbols[-1] if self.selected_symbols else 'NONE'}")
        print(f"rebalance_count={self.rebalance_count}")


def run_strategy(quiet: bool = True):
    quiet_logger = QuietLogger() if quiet else None

    data = build_sample_data()
    exchange = Exchange(logger=quiet_logger)
    exchange.set_data(data, date_key="dt")

    broker = Broker(initial_cash=10_000, fee_rate=0.001, logger=quiet_logger)
    strategy = CrossSectionMomentumStrategy(strategy_id="multi_symbol_rotation", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()
    return strategy, broker


if __name__ == "__main__":
    run_strategy()
