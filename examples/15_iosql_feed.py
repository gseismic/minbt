import os

import matplotlib.pyplot as plt

from minbt import Broker, Exchange, Strategy
from minbt.plugins.binance import BinanceKlineIosqlFeed


SYMBOL = "BTCUSDT"
IOSQL_URI = os.environ.get(
    "MINBT_IOSQL_URI",
    "sqlite:///media/lsl/Z1/findata/crypto/binance/future_usdt/kline.csv.iosql",
)
START = "2023-01-01"
END = "2023-01-03"


class IosqlFeedStrategy(Strategy):
    def on_init(self):
        self.bar_count = 0

    def on_bars(self, dt, bars):
        price = bars[SYMBOL]["close"]
        if self.bar_count == 0:
            self.broker.order_target_percent(SYMBOL, 0.8, price=price)
        self.bar_count += 1

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"bar_count={self.bar_count}")


def run_strategy():
    exchange = Exchange()
    exchange.add_feed(
        BinanceKlineIosqlFeed(
            uri=IOSQL_URI,
            interval="1m",
            symbols=[SYMBOL],
            start=START,
            end=END,
            batch_size=10_000,
        )
    )
    broker = Broker(initial_cash=10_000, fee_rate=0.001)
    strategy = IosqlFeedStrategy(strategy_id="iosql_feed", broker=broker)
    exchange.add_strategy(strategy)
    exchange.run()
    return strategy, broker


if __name__ == "__main__":
    strategy, _ = run_strategy()
    plt.plot(strategy.get_hist_equity())
    plt.title("iosql Feed Equity")
    plt.xlabel("Bar")
    plt.ylabel("Equity")
    plt.show()
