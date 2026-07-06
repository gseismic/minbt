from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import math
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

from example_utils import flatten_position, target_position_value
from minbt import Broker, Exchange, Strategy
from plot_utils import save_figure

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT")


def build_sample_data() -> pd.DataFrame:
    """构造不同阶段强弱切换的多标的行情。"""
    rows = []
    prices = {
        "BTCUSDT": 100.0,
        "ETHUSDT": 100.0,
        "SOLUSDT": 100.0,
        "BNBUSDT": 100.0,
    }
    start_dt = pd.Timestamp("2026-03-01")
    for step in range(72):
        dt = (start_dt + pd.Timedelta(days=step)).date().isoformat()
        for symbol in SYMBOLS:
            if symbol == "BTCUSDT":
                drift = 0.20 + 0.28 * math.sin(step / 11)
            elif symbol == "ETHUSDT":
                drift = 0.10 + (0.55 if 18 <= step < 45 else -0.05) + 0.10 * math.sin(step / 4)
            elif symbol == "SOLUSDT":
                drift = -0.08 + (0.75 if step >= 42 else 0.0) + 0.18 * math.sin(step / 5)
            else:
                drift = 0.08 + 0.08 * math.sin(step / 3)
            prices[symbol] = max(1.0, prices[symbol] + drift)
            rows.append(
                {
                    "dt": dt,
                    "symbol": symbol,
                    "close": round(prices[symbol], 4),
                }
            )
    return pd.DataFrame(rows)


class CrossSectionRotationStrategy(Strategy):
    """多标的横截面动量：定期持有动量最强的两个标的。"""

    def __init__(
        self,
        strategy_id: str,
        broker: Broker,
        lookback: int = 12,
        rebalance_interval: int = 6,
        top_n: int = 2,
        gross_fraction: float = 0.90,
        leverage: float = 1.5,
    ):
        super().__init__(strategy_id=strategy_id, broker=broker)
        self.lookback = lookback
        self.rebalance_interval = rebalance_interval
        self.top_n = top_n
        self.gross_fraction = gross_fraction
        self.leverage = leverage

    def on_init(self):
        self.price_history = defaultdict(lambda: deque(maxlen=self.lookback + 1))
        self.bar_count = 0
        self.rebalance_count = 0
        self.last_selection = []

    def on_bars(self, dt, bars):
        for symbol, row in bars.items():
            self.price_history[symbol].append(float(row["close"]))

        self.bar_count += 1
        enough_history = all(len(self.price_history[symbol]) > self.lookback for symbol in SYMBOLS)
        if not enough_history or self.bar_count % self.rebalance_interval != 0:
            return

        momentum = {}
        for symbol in SYMBOLS:
            prices = list(self.price_history[symbol])
            momentum[symbol] = prices[-1] / prices[0] - 1.0

        selected = sorted(momentum, key=momentum.get, reverse=True)[: self.top_n]
        self.last_selection = selected
        equity = self.broker.get_equity()
        target_value = equity * self.gross_fraction / len(selected)
        changed = False

        for symbol in SYMBOLS:
            price = float(bars[symbol]["close"])
            if symbol in selected:
                changed = target_position_value(
                    self.broker,
                    symbol,
                    target_value,
                    price,
                    leverage=self.leverage,
                ) or changed
            else:
                changed = flatten_position(self.broker, symbol, price) or changed

        if changed:
            self.rebalance_count += 1

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_cash={self.broker.get_cash():.2f}")
        print(f"final_positions={self.broker.get_position_sizes()}")
        print(f"last_selection={self.last_selection}")
        print(f"rebalance_count={self.rebalance_count}")


def run_strategy():
    exchange = Exchange()
    exchange.set_bars(build_sample_data(), date_key="dt")

    broker = Broker(initial_cash=100_000, fee_rate=0.0005, leverage=1.5)
    strategy = CrossSectionRotationStrategy(strategy_id="scenario_multi_rotation", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()

    # ── 绘图：多标的价格 + 权益 ──
    data = build_sample_data()
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
    ax1.set_title("07 Multi-Symbol Rotation — Prices & Equity", fontsize=13, fontweight="bold")
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
    save_figure("07_scenario_multi_rotation")

    return strategy, broker


if __name__ == "__main__":
    run_strategy()
