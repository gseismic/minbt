import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from minbt import Broker, Exchange, Strategy
from minbt.data import IosqlBarsFeed


SYMBOL = "BTCUSDT"
IOSQL_URI = os.environ.get(
    "MINBT_IOSQL_URI",
    "sqlite:///media/lsl/Z1/findata/crypto/binance/future_usdt/kline.csv.iosql",
)
START = "2023-01-01"
END = "2023-01-03"


def _sqlite_path(uri):
    prefix = "sqlite://"
    if uri.startswith(prefix):
        return Path(uri[len(prefix):])
    return None


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
    try:
        import iosql  # noqa: F401
    except ImportError as exc:
        raise SystemExit("iosql is required; install iosql v0.3.x or newer") from exc

    db_path = _sqlite_path(IOSQL_URI)
    if db_path is not None and not db_path.exists():
        raise SystemExit(
            f"iosql database not found: {db_path}\n"
            "Set MINBT_IOSQL_URI to the crypto.bn_data_sync iosql database URI."
        )

    exchange = Exchange()
    exchange.add_feed(
        IosqlBarsFeed(
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
    run_strategy()
