"""订阅 iosql K 线表在指定时间范围内出现的全部 symbol。"""

import os

from minbt import Exchange, Strategy
from minbt.plugins.binance import BinanceKlineIosqlFeed


IOSQL_URI = os.environ.get(
    "MINBT_IOSQL_URI",
    "sqlite:///media/lsl/Z1/findata/crypto/binance/future_usdt/kline.csv.iosql",
)
START = "2023-01-01"
END = "2023-02-03"


class IosqlAllSymbolsStrategy(Strategy):
    def on_init(self):
        self.symbol_bar_counts = {}
        self.callback_count = 0

    def on_bars(self, dt, bars):
        self.callback_count += 1
        for symbol in bars:
            self.symbol_bar_counts[symbol] = self.symbol_bar_counts.get(symbol, 0) + 1

    def on_finish(self):
        symbols = sorted(self.symbol_bar_counts)
        print(f"symbol_count={len(symbols)}")
        print(f"symbols={','.join(symbols)}")
        print(f"kline_count={sum(self.symbol_bar_counts.values())}")
        print(f"callback_count={self.callback_count}")


def run_strategy():
    exchange = Exchange()
    exchange.add_feed(
        BinanceKlineIosqlFeed(
            uri=IOSQL_URI,
            interval="1m",
            symbols="*",
            start=START,
            end=END,
            batch_size=10_000,
        )
    )
    strategy = IosqlAllSymbolsStrategy(strategy_id="iosql_all_symbols")
    exchange.add_strategy(strategy)
    result = exchange.run()
    return result, strategy


if __name__ == "__main__":
    run_strategy()
