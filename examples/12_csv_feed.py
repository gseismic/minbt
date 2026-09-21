import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from minbt import Broker, Exchange, Strategy
from minbt.data import BinanceKlineCsvFeed


SYMBOL = "BTCUSDT"
CSV_ROOT = Path(
    os.environ.get(
        "MINBT_CSV_ROOT",
        "/media/lsl/Z1/findata/crypto/binance/future_usdt/kline.csv/1m",
    )
)
START = "2023-01-01"
END = "2023-01-03"


class CsvFeedStrategy(Strategy):
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
    if not CSV_ROOT.is_dir():
        raise SystemExit(
            f"CSV directory not found: {CSV_ROOT}\n"
            "Set MINBT_CSV_ROOT to the crypto.bn_data_sync kline.csv/<interval> directory."
        )

    exchange = Exchange()
    exchange.add_feed(
        BinanceKlineCsvFeed(
            root=CSV_ROOT,
            symbols=[SYMBOL],
            interval="1m",
            start=START,
            end=END,
        )
    )
    broker = Broker(initial_cash=10_000, fee_rate=0.001)
    strategy = CsvFeedStrategy(strategy_id="csv_feed", broker=broker)
    exchange.add_strategy(strategy)
    exchange.run()
    return strategy, broker


if __name__ == "__main__":
    run_strategy()
