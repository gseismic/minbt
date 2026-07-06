from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import matplotlib
except ImportError:
    raise SystemExit("matplotlib is required for plotting. Install with: pip install minbt[plot]")

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from minbt import Broker, Exchange, Strategy
from plot_utils import save_figure

DATA_PATH = Path(__file__).with_name("data.csv")
SYMBOL = "BTCUSDT"


class MiniStrategy(Strategy):
    """最小单标的示例：开仓一次，固定步数后平仓。"""

    def on_init(self):
        self.step = 0

    def on_bars(self, dt, bars):
        price = bars[SYMBOL]["close"]
        if self.step == 0:
            self.broker.submit_market_order(SYMBOL, qty=0.001, price=price)
        elif self.step == 20:
            self.broker.close_position(SYMBOL, price=price)
        self.step += 1

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_position={self.broker.get_position_size(SYMBOL):.6f}")


def run_strategy():
    data = pd.read_csv(DATA_PATH)
    exchange = Exchange()
    exchange.set_bars(data[["open_time", "symbol", "close"]], date_key="open_time")

    broker = Broker(initial_cash=10_000, fee_rate=0.001)
    strategy = MiniStrategy(strategy_id="mini", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()

    # ── 绘图：价格 + 权益 ──
    sym_bars = data[data["symbol"] == SYMBOL].copy()
    sym_bars["dt"] = pd.to_datetime(sym_bars["open_time"])
    sym_bars = sym_bars.sort_values("dt")

    equity = strategy.get_hist_equity()
    equity = list(equity) if hasattr(equity, "__iter__") else [equity]
    dates = pd.DatetimeIndex(pd.to_datetime(data["open_time"]).unique()).sort_values()
    eq = pd.Series(equity[: len(dates)], index=dates[: len(equity)])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax1.plot(sym_bars["dt"], sym_bars["close"], color="steelblue", linewidth=1.2, label=f"{SYMBOL} close")
    ax1.set_title("01 Demo Mini — Price & Equity", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Price")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)

    ax2.plot(eq.index, eq.values, color="steelblue", linewidth=1.5, label="Equity")
    ax2.axhline(y=eq.iloc[0], color="gray", linestyle="--", alpha=0.5, label="Initial")
    ax2.fill_between(eq.index, eq.iloc[0], eq.values, where=(eq.values >= eq.iloc[0]), color="green", alpha=0.08)
    ax2.fill_between(eq.index, eq.iloc[0], eq.values, where=(eq.values < eq.iloc[0]), color="red", alpha=0.08)
    ax2.set_ylabel("Equity")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left")
    ax2.grid(True, alpha=0.3)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    save_figure("01_demo_mini")

    return strategy, broker


if __name__ == "__main__":
    run_strategy()
