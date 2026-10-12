"""展示通用 Bar、Feed 优先级、Broker 估值和历史回放模式。"""

from datetime import datetime, timezone

import matplotlib.pyplot as plt

from minbt import Bar, Broker, Exchange, Strategy


SYMBOL = "BTCUSDT"


class PriceFeed:
    """只提供估值价格的自定义 Bar Feed。"""

    name = "exchange-mark"
    feed_priority = 20
    supports_preload = True
    supports_incremental = True
    ordered = True

    def events(self):
        for minute, value in ((0, 100.2), (1, 101.2)):
            yield Bar(
                dt=datetime(2026, 1, 1, 0, minute, tzinfo=timezone.utc),
                symbol=SYMBOL,
                kind="price",
                data={"value": value, "source": "exchange_mark"},
            )


class DemoStrategy(Strategy):
    def on_init(self):
        self.steps = 0
        self.callbacks = []

    def on_bars(self, dt, bars):
        self.callbacks.append("bars")
        if self.steps == 0:
            self.broker.submit_market_order(
                SYMBOL,
                qty=0.1,
                price=bars[SYMBOL]["close"],
            )
        self.steps += 1

    def on_books(self, dt, books):
        self.callbacks.append("books")

    def on_bar(self, dt, bar):
        self.callbacks.append(bar.kind)

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"mark_price={self.broker.get_last_price(SYMBOL):.2f}")
        print(f"callbacks={','.join(self.callbacks)}")


def run(mode="auto"):
    exchange = Exchange()
    exchange.set_bars(
        [
            {"dt": "2026-01-01T00:00:00Z", "symbol": SYMBOL, "close": 100.0},
            {"dt": "2026-01-01T00:01:00Z", "symbol": SYMBOL, "close": 101.0},
        ],
        feed_priority=10,
    )
    exchange.set_books(
        [
            {
                "dt": "2026-01-01T00:00:00Z",
                "symbol": SYMBOL,
                "bids": [(99.9, 1.0)],
                "asks": [(100.1, 1.0)],
            },
            {
                "dt": "2026-01-01T00:01:00Z",
                "symbol": SYMBOL,
                "bids": [(100.9, 1.0)],
                "asks": [(101.1, 1.0)],
            },
        ],
        feed_priority=5,
    )
    exchange.add_feed(PriceFeed())

    broker = Broker(
        initial_cash=10_000,
        mark_price="price.value",
    )
    strategy = DemoStrategy(strategy_id="bar-demo", broker=broker)
    exchange.add_strategy(strategy)
    exchange.run(load_mode=mode)
    return strategy, broker


if __name__ == "__main__":
    for mode, style in (("auto", "-"), ("preload", "--"), ("incremental", ":")):
        print(f"load_mode={mode}")
        # 每次 run 都重新创建 Feed、Exchange、Strategy 和 Broker。
        strategy, _ = run(mode)
        plt.plot(strategy.get_hist_equity(), linestyle=style, label=mode)
    plt.title("Replay Mode Equity")
    plt.xlabel("Bar")
    plt.ylabel("Equity")
    plt.legend()
    plt.show()
