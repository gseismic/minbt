import pandas as pd

from example_utils import QuietLogger
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
    """止盈止损示例：下单时设置，持仓过程中可以修改。"""

    def on_init(self):
        self.entered = False
        self.exit_updated = False
        self.position_log = []

    def on_bars(self, dt, bars):
        if not self.entered:
            trail_price = bars[TRAIL_SYMBOL]["close"]
            take_price = bars[TAKE_SYMBOL]["close"]

            self.broker.order_target_percent(
                TRAIL_SYMBOL,
                target_percent=0.4,
                price=trail_price,
                stop_loss=trail_price * 0.95,
                take_profit=trail_price * 1.15,
            )
            self.broker.order_target_percent(
                TAKE_SYMBOL,
                target_percent=0.4,
                price=take_price,
                stop_loss=take_price * 0.95,
                take_profit=take_price * 1.10,
            )
            self.entered = True

        if dt == "2026-03-02" and not self.exit_updated:
            trail_price = bars[TRAIL_SYMBOL]["close"]
            if self.broker.get_position_size(TRAIL_SYMBOL) > 0:
                self.broker.set_exit(
                    TRAIL_SYMBOL,
                    stop_loss=trail_price - 2.0,
                    take_profit=trail_price + 9.0,
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


def run_strategy(quiet: bool = True):
    quiet_logger = QuietLogger() if quiet else None

    exchange = Exchange(logger=quiet_logger)
    exchange.set_bars(build_sample_data(), date_key="dt")

    broker = Broker(initial_cash=10_000, fee_rate=0, logger=quiet_logger)
    strategy = AttachedExitStrategy(strategy_id="scenario_exit_rules", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()
    return strategy, broker


if __name__ == "__main__":
    run_strategy()
