from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collections import defaultdict, deque

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

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def build_sample_data() -> pd.DataFrame:
    """构造一个多标的同时间截面行情样本。"""
    price_paths = {
        "BTCUSDT": [100, 102, 104, 103, 105, 108, 110, 109, 111, 113, 115, 116],
        "ETHUSDT": [100, 101, 100, 102, 104, 107, 111, 114, 118, 121, 119, 122],
        "SOLUSDT": [100, 99, 101, 105, 108, 106, 104, 103, 107, 112, 118, 125],
    }
    rows = []
    for step in range(12):
        dt = f"2026-01-{step + 1:02d}"
        for symbol in SYMBOLS:
            rows.append({"dt": dt, "symbol": symbol, "close": float(price_paths[symbol][step])})
    return pd.DataFrame(rows)


class CrossSectionMomentumStrategy(Strategy):
    """多标的横截面动量轮动示例。"""

    def __init__(
        self,
        strategy_id: str,
        broker: Broker,
        lookback: int = 4,
        target_qty: float = 1.0,
    ):
        super().__init__(strategy_id=strategy_id, broker=broker)
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        self.lookback = lookback
        self.target_qty = target_qty

    def on_init(self):
        self.price_history = defaultdict(lambda: deque(maxlen=self.lookback + 1))
        self.selected_symbols = []
        self.rebalance_count = 0

    def on_bars(self, dt, bars):
        for symbol, row in bars.items():
            self.price_history[symbol].append(row["close"])

        if any(len(self.price_history[symbol]) <= self.lookback for symbol in SYMBOLS):
            return

        momentum = {}
        for symbol in SYMBOLS:
            prices = list(self.price_history[symbol])
            momentum[symbol] = prices[-1] / prices[0] - 1

        selected_symbol = max(momentum, key=momentum.get)
        self.selected_symbols.append(selected_symbol)
        self._rebalance_to(selected_symbol, bars)

    def _rebalance_to(self, selected_symbol: str, bars):
        changed = False
        for symbol in SYMBOLS:
            target_size = self.target_qty if symbol == selected_symbol else 0
            price = float(bars[symbol]["close"])
            order = self.broker.order_target_size(symbol, target_size=target_size, price=price)
            if order.status == "filled":
                changed = True
        if changed:
            self.rebalance_count += 1

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_cash={self.broker.get_cash():.2f}")
        print(f"final_positions={self.broker.get_position_sizes()}")
        print(f"last_selected={self.selected_symbols[-1] if self.selected_symbols else 'NONE'}")
        print(f"rebalance_count={self.rebalance_count}")


def run_strategy():
    data = build_sample_data()
    exchange = Exchange()
    exchange.set_bars(data, date_key="dt")

    broker = Broker(initial_cash=10_000, fee_rate=0.001)
    strategy = CrossSectionMomentumStrategy(strategy_id="multi_symbol_rotation", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()

    # ── 绘图：多标的价格 + 权益 ──
    equity = list(strategy.get_hist_equity())
    dates = pd.DatetimeIndex(pd.to_datetime(data["dt"]).unique()).sort_values()
    eq = pd.Series(equity[: len(dates)], index=dates[: len(equity)])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    colors = plt.cm.tab10(np.linspace(0, 1, len(SYMBOLS)))
    for symbol, color in zip(SYMBOLS, colors):
        sym_bars = data[data["symbol"] == symbol].copy()
        sym_bars["dt"] = pd.to_datetime(sym_bars["dt"])
        sym_bars = sym_bars.sort_values("dt")
        ax1.plot(sym_bars["dt"], sym_bars["close"], color=color, linewidth=1.2, label=symbol)
    ax1.set_title("03 Multi-Symbol Rotation — Prices & Equity", fontsize=13, fontweight="bold")
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
    save_figure("03_multi_symbol_rotation")

    return strategy, broker


if __name__ == "__main__":
    run_strategy()
