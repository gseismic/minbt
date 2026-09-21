from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collections import deque

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


class SingleSymbolSmaStrategy(Strategy):
    """单标的双均线趋势跟随示例。"""

    def __init__(
        self,
        strategy_id: str,
        broker: Broker,
        short_window: int = 12,
        long_window: int = 36,
        target_qty: float = 0.002,
    ):
        super().__init__(strategy_id=strategy_id, broker=broker)
        if short_window <= 0 or long_window <= short_window:
            raise ValueError("short_window must be positive and less than long_window")
        self.short_window = short_window
        self.long_window = long_window
        self.target_qty = target_qty

    def on_init(self):
        self.prices = deque(maxlen=self.long_window)
        self.trade_count = 0

    def on_bars(self, dt, bars):
        price = bars[SYMBOL]["close"]
        self.prices.append(price)
        if len(self.prices) < self.long_window:
            return

        prices = list(self.prices)
        short_ma = sum(prices[-self.short_window:]) / self.short_window
        long_ma = sum(prices) / self.long_window
        target_size = self.target_qty if short_ma > long_ma else -self.target_qty

        order = self.broker.order_target_size(SYMBOL, target_size=target_size, price=price, leverage=2)
        if order.status == "filled":
            self.trade_count += 1

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_cash={self.broker.get_cash():.2f}")
        print(f"final_position={self.broker.get_position_size(SYMBOL):.6f}")
        print(f"trade_count={self.trade_count}")


def run_strategy():
    data = pd.read_csv(DATA_PATH)
    exchange = Exchange()
    exchange.set_bars(data[["open_time", "symbol", "close"]], date_key="open_time")

    broker = Broker(initial_cash=10_000, fee_rate=0.001, leverage=2)
    strategy = SingleSymbolSmaStrategy(strategy_id="single_symbol_sma", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()

    # ── 绘图：价格+双均线 + 权益 ──
    sym_bars = data[data["symbol"] == SYMBOL].copy()
    sym_bars["dt"] = pd.to_datetime(sym_bars["open_time"])
    sym_bars = sym_bars.sort_values("dt")

    ma_short = sym_bars["close"].rolling(12).mean()
    ma_long = sym_bars["close"].rolling(36).mean()

    equity = list(strategy.get_hist_equity())
    pos_sizes = list(strategy.get_hist_position_sizes(SYMBOL))
    dates = pd.DatetimeIndex(pd.to_datetime(data["open_time"]).unique()).sort_values()
    eq = pd.Series(equity[: len(dates)], index=dates[: len(equity)])
    pos = pd.Series(pos_sizes[: len(dates)], index=dates[: len(pos_sizes)])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax1.plot(sym_bars["dt"], sym_bars["close"], color="steelblue", linewidth=1.2, label=f"{SYMBOL} close")
    ax1.plot(sym_bars["dt"], ma_short, color="orange", linewidth=1, label="MA12")
    ax1.plot(sym_bars["dt"], ma_long, color="red", linewidth=1, label="MA36")
    y_min = sym_bars["close"].min()
    y_marker = y_min - (sym_bars["close"].max() - y_min) * 0.05
    long_mask = pos > 0
    short_mask = pos < 0
    if long_mask.any():
        ax1.scatter(pos.index[long_mask], [y_marker] * long_mask.sum(), color="green", marker="^", s=25, alpha=0.6, label="Long")
    if short_mask.any():
        ax1.scatter(pos.index[short_mask], [y_marker] * short_mask.sum(), color="red", marker="v", s=25, alpha=0.6, label="Short")
    ax1.set_title("02 Single Symbol SMA — Price & Equity", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Price")
    ax1.legend(loc="upper left", fontsize="small")
    ax1.grid(True, alpha=0.3)

    ax2.plot(eq.index, eq.values, color="steelblue", linewidth=1.5, label="Equity")
    ax2.axhline(y=eq.iloc[0], color="gray", linestyle="--", alpha=0.5, label="Initial")
    ax2.fill_between(eq.index, eq.iloc[0], eq.values, where=(eq.values >= eq.iloc[0]), color="green", alpha=0.08)
    ax2.fill_between(eq.index, eq.iloc[0], eq.values, where=(eq.values < eq.iloc[0]), color="red", alpha=0.08)
    ax2.set_ylabel("Equity")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left", fontsize="small")
    ax2.grid(True, alpha=0.3)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    save_figure("02_single_symbol_sma")

    return strategy, broker


if __name__ == "__main__":
    run_strategy()
