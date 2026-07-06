from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from minbt import Broker, Exchange, Strategy
from minbt.data import binance

_SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"


def _save_fig(name):
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    p = _SCREENSHOT_DIR / f"{name}.png"
    plt.tight_layout(pad=1.5)
    plt.savefig(str(p), dpi=150, bbox_inches="tight")
    print(f"[plot] saved: {p}")
    plt.close()


SYMBOL = "BTCUSDT"


class BinanceFeedStrategy(Strategy):
    """Binance futures K 线自动下载与缓存示例。"""

    def on_init(self):
        self.has_position = False
        self.bar_count = 0
        self.bar_records = []

    def on_bars(self, dt, bars):
        price = bars[SYMBOL]["close"]
        self.bar_records.append({"dt": dt, "symbol": SYMBOL, "close": price})
        if not self.has_position:
            self.broker.order_target_percent(SYMBOL, 0.8, price=price)
            self.has_position = True
        self.bar_count += 1

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"final_cash={self.broker.get_cash():.2f}")
        print(f"final_position={self.broker.get_position_size(SYMBOL):.6f}")
        print(f"bar_count={self.bar_count}")


def run_strategy():
    exchange = Exchange()
    exchange.add_feed(
        binance.BarsReplayFeed(
            symbols=[SYMBOL],
            interval="1h",
            start="2024-01-01",
            end="2024-01-03",
            cache_dir=Path(__file__).with_name(".cache") / "binance",
        )
    )

    broker = Broker(initial_cash=10_000, fee_rate=0.001)
    strategy = BinanceFeedStrategy(strategy_id="binance_feed", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()

    # ── 绘图：价格 + 权益 ──
    bars_df = pd.DataFrame(strategy.bar_records)
    sym_bars = bars_df[bars_df["symbol"] == SYMBOL].copy()
    sym_bars["dt"] = pd.to_datetime(sym_bars["dt"])
    sym_bars = sym_bars.sort_values("dt")

    equity = list(strategy.get_hist_equity())
    dates = pd.DatetimeIndex(pd.to_datetime(bars_df["dt"]).unique()).sort_values()
    eq = pd.Series(equity[: len(dates)], index=dates[: len(equity)])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax1.plot(sym_bars["dt"], sym_bars["close"], color="steelblue", linewidth=1.2, label=f"{SYMBOL} close")
    ax1.set_title("11 Binance Feed — BTCUSDT Price & Equity", fontsize=13, fontweight="bold")
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
    _save_fig("11_crypto_binance_feed")

    return strategy, broker


if __name__ == "__main__":
    run_strategy()
