from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from minbt import Broker, Exchange, Strategy


TRAIL_SYMBOL = "TRAILCOIN"
TAKE_SYMBOL = "TAKECOIN"


def build_sample_data() -> pd.DataFrame:
    """构造两个标的：一个中途上移止损后触发，另一个直接触发止盈。"""
    return pd.DataFrame(
        [
            {"dt": "2026-03-01", "symbol": TRAIL_SYMBOL, "close": 100.0},
            {"dt": "2026-03-01", "symbol": TAKE_SYMBOL, "close": 100.0},
            {"dt": "2026-03-02", "symbol": TRAIL_SYMBOL, "close": 106.0},
            {"dt": "2026-03-02", "symbol": TAKE_SYMBOL, "close": 112.0},
            {"dt": "2026-03-03", "symbol": TRAIL_SYMBOL, "close": 103.0},
            {"dt": "2026-03-03", "symbol": TAKE_SYMBOL, "close": 113.0},
        ]
    )


class AttachedExitStrategy(Strategy):
    """止盈止损示例：下单时设置，持仓过程中按订单 ID 修改。"""

    def on_init(self):
        self.entered = False
        self.exit_updated = False
        self.trail_order = None
        self.take_order = None
        self.position_log = []

    def on_bars(self, dt, bars):
        if not self.entered:
            trail_price = bars[TRAIL_SYMBOL]["close"]
            take_price = bars[TAKE_SYMBOL]["close"]

            self.trail_order = self.broker.order_target_percent(
                TRAIL_SYMBOL,
                target_percent=0.4,
                price=trail_price,
                stop_loss_price=trail_price * 0.95,
                trailing_stop_pct=0.05,
            )
            self.take_order = self.broker.order_target_percent(
                TAKE_SYMBOL,
                target_percent=0.4,
                price=take_price,
                stop_loss_price=take_price * 0.95,
                take_profit_price=take_price * 1.10,
            )
            self.entered = True

        if dt == "2026-03-02" and not self.exit_updated:
            if self.trail_order is not None and self.broker.get_position_size(TRAIL_SYMBOL) > 0:
                self.broker.set_exit(
                    self.trail_order.id,
                    trailing_stop_amount=2.0,
                )
                self.exit_updated = True

        self.position_log.append(
            {
                "dt": dt,
                TRAIL_SYMBOL: self.broker.get_position_size(TRAIL_SYMBOL),
                TAKE_SYMBOL: self.broker.get_position_size(TAKE_SYMBOL),
            }
        )

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"{TRAIL_SYMBOL}_final_position={self.broker.get_position_size(TRAIL_SYMBOL):.6f}")
        print(f"{TAKE_SYMBOL}_final_position={self.broker.get_position_size(TAKE_SYMBOL):.6f}")
        print(f"exit_updated={self.exit_updated}")
        print(f"position_log={self.position_log}")


def run_strategy():
    exchange = Exchange()
    exchange.set_bars(build_sample_data(), date_key="dt")

    broker = Broker(initial_cash=10_000, fee_rate=0)
    strategy = AttachedExitStrategy(strategy_id="scenario_exit_rules", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()
    return strategy, broker


if __name__ == "__main__":
    run_strategy()
