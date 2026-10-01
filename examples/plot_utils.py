"""示例共享绘图与交互显示工具。"""

import os
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

__all__ = ["plot_feed_price_and_equity", "save_figure"]

_SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"


def _show_enabled():
    value = os.environ.get("MINBT_EXAMPLE_SHOW", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def save_figure(name):
    """保存当前图表，并默认弹窗展示，关闭窗口后继续。"""
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    p = _SCREENSHOT_DIR / f"{name}.png"
    plt.tight_layout(pad=1.5)
    plt.savefig(str(p), dpi=150, bbox_inches="tight")
    print(f"[plot] saved: {p}")
    try:
        if _show_enabled():
            plt.show(block=True)
    finally:
        plt.close()


def plot_feed_price_and_equity(name, title, bar_records, strategy):
    """绘制 Feed/通用 Bar 示例实际回放的价格和账户权益。"""
    if not bar_records:
        raise ValueError("cannot plot an example without price bars")

    records = list(bar_records)
    dates = pd.DatetimeIndex(pd.to_datetime([record["dt"] for record in records]))
    prices = [record["close"] for record in records]
    equity = list(strategy.get_hist_equity())
    count = min(len(dates), len(prices), len(equity))
    if count == 0:
        raise ValueError("cannot plot an example without price or equity history")

    dates = dates[:count]
    prices = prices[:count]
    equity = equity[:count]

    _, (ax_price, ax_equity) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax_price.plot(dates, prices, color="steelblue", linewidth=1.2, label="Close")
    ax_price.set_title(title, fontsize=13, fontweight="bold")
    ax_price.set_ylabel("Price")
    ax_price.legend(loc="upper left")
    ax_price.grid(True, alpha=0.3)

    ax_equity.plot(dates, equity, color="darkorange", linewidth=1.5, label="Equity")
    ax_equity.axhline(y=equity[0], color="gray", linestyle="--", alpha=0.5, label="Initial")
    ax_equity.set_ylabel("Equity")
    ax_equity.set_xlabel("Date")
    ax_equity.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax_equity.legend(loc="upper left")
    ax_equity.grid(True, alpha=0.3)
    save_figure(name)
