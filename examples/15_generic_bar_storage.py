"""演示 CSV 作为通用 Bar 存储，而不是 Kline 专用格式。"""

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from minbt import Broker, Exchange, Strategy  # noqa: E402
from minbt.data import CsvBarFeed  # noqa: E402


SYMBOL = "BTCUSDT"


class GenericBarStrategy(Strategy):
    def on_init(self):
        self.entered = False
        self.seen = []

    def on_bar(self, dt, bar):
        self.seen.append(bar.kind)
        if bar.kind == "price" and not self.entered:
            self.broker.submit_market_order(
                SYMBOL,
                qty=0.1,
                price=bar.data["value"],
            )
            self.entered = True

    def on_books(self, dt, books):
        self.seen.append("orderbook")

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"bar_kinds={','.join(self.seen)}")


def run():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "bars.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["dt", "symbol", "kind", "data"])
            writer.writeheader()
            writer.writerow(
                {
                    "dt": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
                    "symbol": SYMBOL,
                    "kind": "orderbook",
                    "data": json.dumps({"bids": [[100.0, 1.0]], "asks": [[100.1, 1.0]]}),
                }
            )
            writer.writerow(
                {
                    "dt": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
                    "symbol": SYMBOL,
                    "kind": "price",
                    "data": json.dumps({"value": 100.0, "source": "mark"}),
                }
            )
            writer.writerow(
                {
                    "dt": datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc).isoformat(),
                    "symbol": SYMBOL,
                    "kind": "price",
                    "data": json.dumps({"value": 101.0, "source": "mark"}),
                }
            )

        exchange = Exchange()
        exchange.add_feed(CsvBarFeed(path))
        broker = Broker(initial_cash=10_000, mark_price="price.value")
        exchange.add_strategy(GenericBarStrategy("generic-bar", broker))
        exchange.run()
        return broker


if __name__ == "__main__":
    run()
