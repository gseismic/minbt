"""展示通用 Bar、Feed 优先级、Broker 估值和历史回放模式。"""

from datetime import datetime, timezone
try:
    import matplotlib  # noqa: F401
except ImportError as exc:
    raise SystemExit("matplotlib is required for plotting. Install with: pip install minbt[plot]") from exc

from minbt import Bar, Broker, Exchange, Strategy
from plot_utils import plot_feed_price_and_equity


SYMBOL = "BTCUSDT"


class PriceFeed:
    """只提供估值价格的自定义 Bar Feed。"""

    name = "exchange-mark"
    feed_priority = 20
    supports_preload = True
    supports_incremental = True
    ordered = True
    replayable = True

    def events(self):
        for minute, value in ((0, 100.2), (1, 101.2)):
            yield Bar(
                dt=datetime(2026, 1, 1, 0, minute, tzinfo=timezone.utc),
                symbol=SYMBOL,
                kind="price",
                data={"value": value, "source": "exchange_mark"},
            )

    def prepare(self):
        return None

    def close(self):
        return None


class DemoStrategy(Strategy):
    def on_init(self):
        self.steps = 0
        self.bar_records = []

    def on_bars(self, dt, bars):
        self.bar_records.append({"dt": dt, "symbol": SYMBOL, "close": bars[SYMBOL]["close"]})
        if self.steps == 0:
            self.broker.submit_market_order(
                SYMBOL,
                qty=0.1,
                price=bars[SYMBOL]["close"],
            )
        self.steps += 1

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"mark_price={self.broker.get_last_price(SYMBOL):.2f}")


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
    plot_feed_price_and_equity(
        "400_exchange_replay_modes",
        "400 Replay Modes — BTCUSDT Price & Equity",
        strategy.bar_records,
        strategy,
    )
    return broker


if __name__ == "__main__":
    run()
