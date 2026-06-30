from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from minbt import Broker, Exchange, Strategy


DATA_PATH = Path(__file__).with_name("data.csv")
SYMBOL = "BTCUSDT"


class MiniStrategy(Strategy):
    """最小单标的示例：开仓一次，固定步数后平仓。"""

    def on_init(self):
        self.step = 0

    def on_bars(self, dt, bars):
        price = bars[SYMBOL]["close"]
        if self.step == 0:
            self.broker.submit_market_order(SYMBOL, qty=0.001, price=price)
        elif self.step == 20:
            self.broker.close_position(SYMBOL, price=price)
        self.step += 1

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_position={self.broker.get_position_size(SYMBOL):.6f}")


def run_strategy():
    data = pd.read_csv(DATA_PATH)
    exchange = Exchange()
    exchange.set_bars(data[["date", "symbol", "close"]], date_key="date")

    broker = Broker(initial_cash=10_000, fee_rate=0.001)
    strategy = MiniStrategy(strategy_id="mini", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()
    return strategy, broker


if __name__ == "__main__":
    run_strategy()
