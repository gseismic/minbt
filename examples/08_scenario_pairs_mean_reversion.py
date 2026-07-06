import math
from collections import deque
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from example_utils import target_position_value
from minbt import Broker, Exchange, Strategy

_SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"


def _save_fig(name):
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    p = _SCREENSHOT_DIR / f"{name}.png"
    plt.tight_layout(pad=1.5)
    plt.savefig(str(p), dpi=150, bbox_inches="tight")
    print(f"[plot] saved: {p}")
    plt.close()


BASE_SYMBOL = "BTCUSDT"
PAIR_SYMBOL = "ETHUSDT"
SYMBOLS = (BASE_SYMBOL, PAIR_SYMBOL)


def build_sample_data() -> pd.DataFrame:
    """构造两个长期相关、短期价差周期偏离的标的。"""
    rows = []
    base_price = 100.0
    start_dt = pd.Timestamp("2026-04-01")
    for step in range(90):
        base_price += 0.18 + 0.10 * math.sin(step / 12)
        spread = 0.055 * math.sin(step / 5) + 0.018 * math.sin(step / 2)
        pair_price = base_price * (1.0 + spread)
        dt = (start_dt + pd.Timedelta(days=step)).date().isoformat()
        rows.append({"dt": dt, "symbol": BASE_SYMBOL, "close": round(base_price, 4)})
        rows.append({"dt": dt, "symbol": PAIR_SYMBOL, "close": round(pair_price, 4)})
    return pd.DataFrame(rows)


class PairMeanReversionStrategy(Strategy):
    """配对均值回归：价差过宽时做空强腿、做多弱腿。"""

    def __init__(
        self,
        strategy_id: str,
        broker: Broker,
        spread_window: int = 20,
        entry_z: float = 1.25,
        exit_z: float = 0.25,
        leg_fraction: float = 0.35,
        leverage: float = 2.0,
    ):
        super().__init__(strategy_id=strategy_id, broker=broker)
        self.spread_window = spread_window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.leg_fraction = leg_fraction
        self.leverage = leverage

    def on_init(self):
        self.spreads = deque(maxlen=self.spread_window)
        self.state = "flat"
        self.entry_count = 0
        self.exit_count = 0
        self.last_z = 0.0

    def on_bars(self, dt, bars):
        base_price = float(bars[BASE_SYMBOL]["close"])
        pair_price = float(bars[PAIR_SYMBOL]["close"])
        spread = math.log(pair_price / base_price)

        if len(self.spreads) >= self.spread_window:
            values = list(self.spreads)
            mean = sum(values) / len(values)
            variance = sum((value - mean) ** 2 for value in values) / len(values)
            std = math.sqrt(variance)
            self.last_z = 0.0 if std == 0 else (spread - mean) / std
            self._trade_by_z_score(self.last_z, base_price, pair_price)

        self.spreads.append(spread)

    def _trade_by_z_score(self, z_score: float, base_price: float, pair_price: float):
        equity = self.broker.get_equity()
        leg_value = equity * self.leg_fraction

        if self.state == "flat":
            if z_score > self.entry_z:
                # pair rich: short pair, long base
                self._set_pair(base_value=leg_value, pair_value=-leg_value, base_price=base_price, pair_price=pair_price)
                self.state = "short_pair"
                self.entry_count += 1
            elif z_score < -self.entry_z:
                # pair cheap: long pair, short base
                self._set_pair(base_value=-leg_value, pair_value=leg_value, base_price=base_price, pair_price=pair_price)
                self.state = "long_pair"
                self.entry_count += 1
        elif abs(z_score) < self.exit_z:
            self._set_pair(base_value=0.0, pair_value=0.0, base_price=base_price, pair_price=pair_price)
            self.state = "flat"
            self.exit_count += 1

    def _set_pair(self, base_value: float, pair_value: float, base_price: float, pair_price: float):
        target_position_value(
            self.broker,
            BASE_SYMBOL,
            base_value,
            base_price,
            leverage=self.leverage,
        )
        target_position_value(
            self.broker,
            PAIR_SYMBOL,
            pair_value,
            pair_price,
            leverage=self.leverage,
        )

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_cash={self.broker.get_cash():.2f}")
        print(f"final_positions={self.broker.get_position_sizes()}")
        print(f"state={self.state}")
        print(f"entry_count={self.entry_count}")
        print(f"exit_count={self.exit_count}")
        print(f"last_z={self.last_z:.4f}")


def run_strategy():
    exchange = Exchange()
    exchange.set_bars(build_sample_data(), date_key="dt")

    broker = Broker(initial_cash=100_000, fee_rate=0.0005, leverage=2.0)
    strategy = PairMeanReversionStrategy(strategy_id="scenario_pairs_mean_reversion", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()

    # ── 绘图：价差+z-score + 权益 ──
    data = build_sample_data()
    base_bars = data[data["symbol"] == BASE_SYMBOL].copy()
    pair_bars = data[data["symbol"] == PAIR_SYMBOL].copy()
    base_bars["dt"] = pd.to_datetime(base_bars["dt"])
    pair_bars["dt"] = pd.to_datetime(pair_bars["dt"])
    base_bars = base_bars.sort_values("dt").set_index("dt")
    pair_bars = pair_bars.sort_values("dt").set_index("dt")

    common_idx = base_bars.index.intersection(pair_bars.index)
    spread = np.log(pair_bars.loc[common_idx, "close"] / base_bars.loc[common_idx, "close"])
    spread_mean = spread.rolling(20).mean()
    spread_std = spread.rolling(20).std()
    z_score = (spread - spread_mean) / spread_std.replace(0, np.nan)

    equity = list(strategy.get_hist_equity())
    dates = pd.DatetimeIndex(pd.to_datetime(data["dt"]).unique()).sort_values()
    eq = pd.Series(equity[: len(dates)], index=dates[: len(equity)])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax1.plot(common_idx, spread, color="steelblue", linewidth=1, label="Log Spread")
    ax1_twin = ax1.twinx()
    ax1_twin.plot(common_idx, z_score, color="red", linewidth=0.8, alpha=0.7, label="Z-Score")
    ax1_twin.axhline(y=1.25, color="green", linestyle="--", alpha=0.5, label="Entry ±1.25")
    ax1_twin.axhline(y=-1.25, color="green", linestyle="--", alpha=0.5)
    ax1_twin.axhline(y=0, color="gray", linestyle=":", alpha=0.5)
    ax1_twin.axhline(y=0.25, color="orange", linestyle="--", alpha=0.4, label="Exit ±0.25")
    ax1_twin.axhline(y=-0.25, color="orange", linestyle="--", alpha=0.4)
    ax1.set_title("08 Pairs Mean Reversion — Spread, Z-Score & Equity", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Log Spread")
    ax1_twin.set_ylabel("Z-Score")
    ax1.legend(loc="upper left", fontsize="small")
    ax1_twin.legend(loc="upper right", fontsize="small")
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
    _save_fig("08_scenario_pairs_mean_reversion")

    return strategy, broker


if __name__ == "__main__":
    run_strategy()
