from pathlib import Path
import sys

try:
    import matplotlib
except ImportError:
    raise SystemExit("matplotlib is required for plotting. Install with: pip install minbt[plot]")

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from minbt import Broker, Exchange, Strategy, markets
from plot_utils import save_figure

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

    # ── 绘图：跨市场价格 + 权益 ──
    data = build_sample_data()
    equity = list(strategy.get_hist_equity())
    dates = pd.DatetimeIndex(pd.to_datetime(data["dt"]).unique()).sort_values()
    eq = pd.Series(equity[: len(dates)], index=dates[: len(equity)])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    for symbol, color, ls in [(SYMBOL_A, "steelblue", "-"), (SYMBOL_C, "darkorange", "--")]:
        sym_bars = data[data["symbol"] == symbol].copy()
        sym_bars["dt"] = pd.to_datetime(sym_bars["dt"])
        sym_bars = sym_bars.sort_values("dt")
        ax1.plot(sym_bars["dt"], sym_bars["close"], color=color, linestyle=ls, linewidth=1.5, marker="o", markersize=4, label=symbol)
    ax1.set_title("10 Cross-Market — A-Share & Crypto Prices + Equity", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Price")
    ax1.legend(loc="upper left", fontsize="small")
    ax1.grid(True, alpha=0.3)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    ax2.plot(eq.index, eq.values, color="steelblue", linewidth=1.5, label="Total Equity")
    ax2.axhline(y=eq.iloc[0], color="gray", linestyle="--", alpha=0.5)
    ax2.fill_between(eq.index, eq.iloc[0], eq.values, where=(eq.values >= eq.iloc[0]), color="green", alpha=0.08)
    ax2.fill_between(eq.index, eq.iloc[0], eq.values, where=(eq.values < eq.iloc[0]), color="red", alpha=0.08)
    ax2.set_ylabel("Equity")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left", fontsize="small")
    ax2.grid(True, alpha=0.3)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    save_figure("10_scenario_cross_market")

    return strategy, broker


if __name__ == "__main__":
    run_strategy()
