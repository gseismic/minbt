from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import math
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

from example_utils import target_position_value
from minbt import Broker, Exchange, Strategy
from plot_utils import save_figure

SYMBOL = "BTCUSDT"


def build_sample_data() -> pd.DataFrame:
    """构造带有盘整、突破、回撤和二次趋势的单标的行情。"""
    rows = []
    close = 100.0
    start_dt = pd.Timestamp("2026-02-01")
    for step in range(96):
        if step < 24:
            drift = 0.04 * math.sin(step / 2)
        elif step < 54:
            drift = 0.55 + 0.12 * math.sin(step / 3)
        elif step < 72:
            drift = -0.45 + 0.18 * math.sin(step / 2)
        else:
            drift = 0.34 + 0.08 * math.sin(step / 4)
        close = max(1.0, close + drift)
        daily_range = 0.7 + 0.25 * abs(math.sin(step / 5))
        rows.append(
            {
                "dt": (start_dt + pd.Timedelta(days=step)).date().isoformat(),
                "symbol": SYMBOL,
                "open": round(close - drift, 4),
                "high": round(close + daily_range, 4),
                "low": round(close - daily_range, 4),
                "close": round(close, 4),
            }
        )
    return pd.DataFrame(rows)


class BreakoutWithStopStrategy(Strategy):
    """单标的趋势突破：突破入场，波动止损，目标名义金额调仓。"""

    def __init__(
        self,
        strategy_id: str,
        broker: Broker,
        lookback: int = 18,
        atr_window: int = 10,
        target_fraction: float = 0.75,
        leverage: float = 2.0,
    ):
        super().__init__(strategy_id=strategy_id, broker=broker)
        self.lookback = lookback
        self.atr_window = atr_window
        self.target_fraction = target_fraction
        self.leverage = leverage

    def on_init(self):
        self.closes = deque(maxlen=self.lookback + 1)
        self.true_ranges = deque(maxlen=self.atr_window)
        self.prev_close = None
        self.entry_price = None
        self.highest_close = None
        self.trade_count = 0
        self.stop_count = 0

    def on_bars(self, dt, bars):
        row = bars[SYMBOL]
        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])
        if self.prev_close is not None:
            true_range = max(high - low, abs(high - self.prev_close), abs(low - self.prev_close))
            self.true_ranges.append(true_range)

        if len(self.closes) >= self.lookback and len(self.true_ranges) >= self.atr_window:
            atr = sum(self.true_ranges) / len(self.true_ranges)
            previous_closes = list(self.closes)
            current_size = self.broker.get_position_size(SYMBOL)

            if current_size > 0:
                self.highest_close = max(self.highest_close or close, close)
                stop_price = max(self.entry_price - 2.0 * atr, self.highest_close - 3.0 * atr)
                if close < stop_price:
                    if target_position_value(self.broker, SYMBOL, 0.0, close, leverage=self.leverage):
                        self.stop_count += 1
                        self.trade_count += 1
                    self.entry_price = None
                    self.highest_close = None
            else:
                breakout = close > max(previous_closes[-self.lookback:])
                volatility_ok = atr / close < 0.04
                if breakout and volatility_ok:
                    target_value = self.broker.get_equity() * self.target_fraction
                    if target_position_value(self.broker, SYMBOL, target_value, close, leverage=self.leverage):
                        self.entry_price = close
                        self.highest_close = close
                        self.trade_count += 1

        self.closes.append(close)
        self.prev_close = close

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_cash={self.broker.get_cash():.2f}")
        print(f"final_position={self.broker.get_position_size(SYMBOL):.6f}")
        print(f"trade_count={self.trade_count}")
        print(f"stop_count={self.stop_count}")


def run_strategy():
    exchange = Exchange()
    exchange.set_bars(build_sample_data(), date_key="dt")

    broker = Broker(initial_cash=100_000, fee_rate=0.0005, leverage=2.0)
    strategy = BreakoutWithStopStrategy(strategy_id="scenario_single_breakout", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()

    # ── 绘图：价格+突破高亮 + 权益 ──
    data = build_sample_data()
    sym_bars = data[data["symbol"] == SYMBOL].copy()
    sym_bars["dt"] = pd.to_datetime(sym_bars["dt"])
    sym_bars = sym_bars.sort_values("dt")

    equity = list(strategy.get_hist_equity())
    dates = pd.DatetimeIndex(pd.to_datetime(data["dt"]).unique()).sort_values()
    eq = pd.Series(equity[: len(dates)], index=dates[: len(equity)])

    rolling_max = sym_bars["close"].rolling(18).max()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax1.plot(sym_bars["dt"], sym_bars["close"], color="steelblue", linewidth=1.2, label=f"{SYMBOL} close")
    ax1.plot(sym_bars["dt"], rolling_max, color="orange", linestyle="--", linewidth=0.8, alpha=0.7, label="Rolling High (18)")
    ax1.set_title("06 Single Breakout — Price & Equity", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Price")
    ax1.legend(loc="upper left", fontsize="small")
    ax1.grid(True, alpha=0.3)

    ax2.plot(eq.index, eq.values, color="steelblue", linewidth=1.5, label="Equity")
    ax2.axhline(y=eq.iloc[0], color="gray", linestyle="--", alpha=0.5)
    ax2.fill_between(eq.index, eq.iloc[0], eq.values, where=(eq.values >= eq.iloc[0]), color="green", alpha=0.08)
    ax2.fill_between(eq.index, eq.iloc[0], eq.values, where=(eq.values < eq.iloc[0]), color="red", alpha=0.08)
    ax2.set_ylabel("Equity")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left", fontsize="small")
    ax2.grid(True, alpha=0.3)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    save_figure("06_scenario_single_breakout")

    return strategy, broker


if __name__ == "__main__":
    run_strategy()
