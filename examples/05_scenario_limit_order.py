from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from minbt import Broker, Exchange, Strategy


SYMBOL = "BTCUSDT"


def build_sample_data() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"dt": "2026-05-01", "symbol": SYMBOL, "close": 100.0},
            {"dt": "2026-05-02", "symbol": SYMBOL, "close": 99.0},
            {"dt": "2026-05-03", "symbol": SYMBOL, "close": 96.0},
            {"dt": "2026-05-04", "symbol": SYMBOL, "close": 94.0},
            {"dt": "2026-05-05", "symbol": SYMBOL, "close": 97.0},
            {"dt": "2026-05-06", "symbol": SYMBOL, "close": 105.0},
        ]
    )


class LimitOrderStrategy(Strategy):
    """限价单示例：挂单、成交、订单级止盈退出。"""

    def on_init(self):
        self.limit_order = None
        self.position_log = []

    def on_bars(self, dt, bars):
        price = bars[SYMBOL]["close"]
        if self.limit_order is None:
            self.limit_order = self.broker.submit_limit_order(
                SYMBOL,
                qty=1,
                limit_price=95,
                stop_loss_price=90,
                take_profit_price=104,
            )
        self.position_log.append((dt, price, self.broker.get_position_size(SYMBOL)))

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"limit_order_status={self.limit_order.status}")
        print(f"final_position={self.broker.get_position_size(SYMBOL):.6f}")
        print(f"position_log={self.position_log}")


def run_strategy():
    exchange = Exchange()
    exchange.set_bars(build_sample_data())

    broker = Broker(initial_cash=1_000, fee_rate=0)
    strategy = LimitOrderStrategy(strategy_id="scenario_limit_order", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()
    return strategy, broker


if __name__ == "__main__":
    run_strategy()
