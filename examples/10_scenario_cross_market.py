from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from minbt import Broker, Exchange, Strategy, markets


SYMBOL_A = "600519.SH"
SYMBOL_C = "BTCUSDT"


def build_sample_data() -> pd.DataFrame:
    """构造 A 股 + crypto 的同一时间截面日线数据。"""
    rows = []
    a_prices = [100.00, 101.20, 100.80, 102.40, 103.00]
    c_prices = [40000.0, 40800.0, 40200.0, 41500.0, 42000.0]
    for index, dt in enumerate(pd.date_range("2026-01-05", periods=5, freq="D")):
        rows.append({"dt": dt.date().isoformat(), "symbol": SYMBOL_A, "close": a_prices[index]})
        rows.append({"dt": dt.date().isoformat(), "symbol": SYMBOL_C, "close": c_prices[index]})
    return pd.DataFrame(rows)


class CrossMarketAllocationStrategy(Strategy):
    """一个 Broker 内同时交易 A 股和 crypto，市场规则按 symbol 路由。"""

    def on_init(self):
        self.bar_count = 0

    def on_bars(self, dt, bars):
        a_price = float(bars[SYMBOL_A]["close"])
        c_price = float(bars[SYMBOL_C]["close"])

        if self.bar_count < 4:
            self.broker.order_target_percent(SYMBOL_A, 0.8, price=a_price, portfolio="ashare")
            self.broker.order_target_percent(SYMBOL_C, 0.8, price=c_price, portfolio="crypto")
        else:
            self.broker.close_position(SYMBOL_A, price=a_price, portfolio="ashare")
            self.broker.close_position(SYMBOL_C, price=c_price, portfolio="crypto")

        self.bar_count += 1

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"ashare_cash={self.broker.get_cash('ashare'):.2f}")
        print(f"crypto_cash={self.broker.get_cash('crypto'):.2f}")
        print(f"ashare_positions={self.broker.get_position_sizes('ashare')}")
        print(f"crypto_positions={self.broker.get_position_sizes('crypto')}")


def run_strategy():
    exchange = Exchange()
    exchange.set_bars(build_sample_data(), date_key="dt")

    broker = Broker(initial_cash=100_000, fee_rate=0.0005, market=markets.CRYPTO)
    broker.add_portfolio("ashare", cash=60_000)
    broker.add_portfolio("crypto", cash=40_000)
    broker.add_market("AStock", markets.A_STOCK, symbols=[SYMBOL_A])

    strategy = CrossMarketAllocationStrategy(strategy_id="scenario_cross_market", broker=broker)
    exchange.add_strategy(strategy)
    exchange.run()
    return strategy, broker


if __name__ == "__main__":
    run_strategy()
