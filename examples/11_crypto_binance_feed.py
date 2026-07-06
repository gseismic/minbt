from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from minbt import Broker, Exchange, Strategy
from minbt.data import binance


SYMBOL = "BTCUSDT"


class BinanceFeedStrategy(Strategy):
    """Binance futures K 线自动下载与缓存示例。"""

    def on_init(self):
        self.has_position = False
        self.bar_count = 0

    def on_bars(self, dt, bars):
        price = bars[SYMBOL]["close"]
        if not self.has_position:
            self.broker.order_target_percent(SYMBOL, 0.8, price=price)
            self.has_position = True
        self.bar_count += 1

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_cash={self.broker.get_cash():.2f}")
        print(f"final_position={self.broker.get_position_size(SYMBOL):.6f}")
        print(f"bar_count={self.bar_count}")


def run_strategy():
    exchange = Exchange()
    exchange.add_feed(
        binance.BarsReplayFeed(
            symbols=[SYMBOL],
            interval="1h",
            start="2024-01-01",
            end="2024-01-03",
            cache_dir=Path(__file__).with_name(".cache") / "binance",
        )
    )

    broker = Broker(initial_cash=10_000, fee_rate=0.001)
    strategy = BinanceFeedStrategy(strategy_id="binance_feed", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()
    return strategy, broker


if __name__ == "__main__":
    run_strategy()
