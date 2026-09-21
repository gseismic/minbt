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
import numpy as np
import pandas as pd

from minbt import Broker, Exchange, Strategy
from plot_utils import save_figure

SYMBOL = "BTCUSDT"


def build_sample_data() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"dt": "2026-05-01", "symbol": SYMBOL, "close": 100.0},
            {"dt": "2026-05-02", "symbol": SYMBOL, "close": 99.0},
            {"dt": "2026-05-03", "symbol": SYMBOL, "close": 96.0},
            {"dt": "2026-05-04", "symbol": SYMBOL, "close": 94.0},
            {"dt": "2026-05-05", "symbol": SYMBOL, "close": 97.0},
            {"dt": "2026-05-06", "symbol": SYMBOL, "close": 105.0},
        ]
    )


class LimitOrderStrategy(Strategy):
    """限价单示例：挂单、成交、订单级止盈退出。"""

    def on_init(self):
        self.limit_order = None
        self.position_log = []

    def on_bars(self, dt, bars):
        price = bars[SYMBOL]["close"]
        if self.limit_order is None:
            self.limit_order = self.broker.submit_limit_order(
                SYMBOL,
                qty=1,
                limit_price=95,
                stop_loss_price=90,
                take_profit_price=104,
            )
        self.position_log.append((dt, price, self.broker.get_position_size(SYMBOL)))

    def on_finish(self):
        print(f"final_equity={self.broker.get_total_equity():.2f}")
        print(f"limit_order_status={self.limit_order.status}")
        print(f"final_position={self.broker.get_position_size(SYMBOL):.6f}")
        print(f"position_log={self.position_log}")


def run_strategy():
    exchange = Exchange()
    exchange.set_bars(build_sample_data())

    broker = Broker(initial_cash=1_000, fee_rate=0)
    strategy = LimitOrderStrategy(strategy_id="scenario_limit_order", broker=broker)

    exchange.add_strategy(strategy)
    exchange.run()

    # ── 绘图：价格 + 持仓 ──
    data = build_sample_data()
    sym_bars = data[data["symbol"] == SYMBOL].copy()
    sym_bars["dt"] = pd.to_datetime(sym_bars["dt"])
    sym_bars = sym_bars.sort_values("dt")

    equity = list(strategy.get_hist_equity())
    pos_sizes = list(strategy.get_hist_position_sizes(SYMBOL))
    dates = pd.DatetimeIndex(pd.to_datetime(data["dt"]).unique()).sort_values()
    eq = pd.Series(equity[: len(dates)], index=dates[: len(equity)])
    pos = pd.Series(pos_sizes[: len(dates)], index=dates[: len(pos_sizes)])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax1.plot(sym_bars["dt"], sym_bars["close"], color="steelblue", linewidth=1.2, marker="o", markersize=5, label=f"{SYMBOL} close")
    ax1.axhline(y=95, color="orange", linestyle="--", alpha=0.7, label="Limit 95")
    ax1.set_title("05 Limit Order — Price & Position", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Price")
    ax1.legend(loc="upper left", fontsize="small")
    ax1.grid(True, alpha=0.3)

    ax2.fill_between(pos.index, 0, pos.values, color="steelblue", alpha=0.2)
    ax2.plot(pos.index, pos.values, color="steelblue", linewidth=1.5, marker=".", markersize=6, label="Position")
    ax2.set_ylabel("Position Size")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left", fontsize="small")
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=0, color="black", linewidth=0.5)
    save_figure("05_scenario_limit_order")

    return strategy, broker


if __name__ == "__main__":
    run_strategy()
