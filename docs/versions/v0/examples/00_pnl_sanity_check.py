"""用可手算的最小场景校验 minbt 的多空盈亏和手续费。"""

from pathlib import Path
import math
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_EXAMPLES_DIR = Path(__file__).resolve().parent
if str(_EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES_DIR))

try:
    import matplotlib
except ImportError:
    raise SystemExit("matplotlib is required for plotting. Install with: pip install minbt[plot]")

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

from minbt import Broker, Exchange, Strategy
from plot_utils import save_figure


INITIAL_CASH = 1_000.0
SYMBOL = "TEST"

SCENARIOS = (
    {
        "name": "long_profit",
        "label": "多头盈利",
        "prices": (100.0, 110.0, 120.0),
        "qty": 1.0,
        "fee_rate": 0.0,
    },
    {
        "name": "short_profit",
        "label": "空头盈利",
        "prices": (100.0, 95.0, 90.0),
        "qty": -1.0,
        "fee_rate": 0.0,
    },
    {
        "name": "fees_turn_small_gain_into_loss",
        "label": "手续费覆盖小幅上涨",
        "prices": (100.0, 100.05),
        "qty": 1.0,
        "fee_rate": 0.001,
    },
)


class FixedTradeStrategy(Strategy):
    """在第一根 bar 开仓，在最后一根 bar 平仓。"""

    def __init__(self, strategy_id: str, broker: Broker, qty: float, exit_step: int):
        super().__init__(strategy_id=strategy_id, broker=broker)
        self.qty = qty
        self.exit_step = exit_step
        self.step = 0
        self.entry_order = None
        self.exit_order = None

    def on_bars(self, dt, bars):
        price = bars[SYMBOL]["close"]
        if self.step == 0:
            self.entry_order = self.broker.submit_market_order(
                SYMBOL,
                qty=self.qty,
                price=price,
                price_dt=dt,
            )
        elif self.step == self.exit_step:
            self.exit_order = self.broker.close_position(
                SYMBOL,
                price=price,
                price_dt=dt,
            )
        self.step += 1


def build_sample_data(prices) -> pd.DataFrame:
    """构造只包含 dt、symbol、close 的最小 bars 数据。"""
    return pd.DataFrame(
        [
            {
                "dt": f"2026-01-{index + 1:02d}",
                "symbol": SYMBOL,
                "close": price,
            }
            for index, price in enumerate(prices)
        ]
    )


def expected_pnl(qty: float, prices, fee_rate: float) -> dict:
    """按单次往返交易的手算公式计算毛盈亏、手续费和净盈亏。"""
    entry_price = prices[0]
    exit_price = prices[-1]
    gross_pnl = qty * (exit_price - entry_price)
    fees = abs(qty) * (entry_price + exit_price) * fee_rate
    return {
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_pnl": gross_pnl - fees,
    }


def run_scenario(config: dict) -> dict:
    """运行一个场景并返回权益、净盈亏和理论值。"""
    prices = tuple(config["prices"])
    data = build_sample_data(prices)
    broker = Broker(initial_cash=INITIAL_CASH, fee_rate=config["fee_rate"])
    strategy = FixedTradeStrategy(
        strategy_id=config["name"],
        broker=broker,
        qty=config["qty"],
        exit_step=len(prices) - 1,
    )

    exchange = Exchange()
    exchange.set_bars(data)
    exchange.add_strategy(strategy)
    exchange.run()

    if strategy.entry_order is None or strategy.entry_order.status != "filled":
        raise AssertionError(f"entry order was not filled: {strategy.entry_order}")
    if strategy.exit_order is None or strategy.exit_order.status != "filled":
        raise AssertionError(f"exit order was not filled: {strategy.exit_order}")

    equity = [float(value) for value in strategy.get_hist_equity()]
    pnl = [value - INITIAL_CASH for value in equity]
    hand_calculation = expected_pnl(config["qty"], prices, config["fee_rate"])
    actual_pnl = pnl[-1]
    if not math.isclose(actual_pnl, hand_calculation["net_pnl"], rel_tol=1e-9, abs_tol=1e-9):
        raise AssertionError(
            f"{config['name']} pnl mismatch: expected={hand_calculation['net_pnl']}, actual={actual_pnl}"
        )

    return {
        "name": config["name"],
        "label": config["label"],
        "dates": pd.DatetimeIndex(pd.to_datetime(data["dt"])),
        "equity": equity,
        "pnl": pnl,
        "final_equity": broker.get_total_equity(),
        "actual_pnl": actual_pnl,
        **hand_calculation,
    }


def plot_pnl_curves(results) -> None:
    """绘制各场景的净盈亏曲线，并以零线区分盈利和亏损。"""
    fig, ax = plt.subplots(figsize=(11, 6))
    colors = ("#16803c", "#2563eb", "#c2410c")

    for result, color in zip(results, colors):
        dates = result["dates"]
        pnl = result["pnl"]
        ax.fill_between(
            dates,
            0,
            pnl,
            where=[value >= 0 for value in pnl],
            color=color,
            alpha=0.08,
        )
        ax.fill_between(
            dates,
            0,
            pnl,
            where=[value < 0 for value in pnl],
            color="#dc2626",
            alpha=0.08,
        )
        ax.plot(dates, pnl, marker="o", linewidth=2, color=color, label=result["name"])
        ax.scatter(dates[-1], pnl[-1], color=color, s=45, zorder=3)
        ax.annotate(
            f"{pnl[-1]:+.5f}",
            (dates[-1], pnl[-1]),
            xytext=(6, 6),
            textcoords="offset points",
            color=color,
        )

    ax.axhline(0.0, color="black", linestyle="--", linewidth=1, label="Zero P&L")
    ax.set_title("00 P&L Sanity Check - Net P&L Curve", fontsize=14, fontweight="bold")
    ax.set_ylabel("Net P&L (Equity - Initial Cash)")
    ax.set_xlabel("Date")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda value, _: f"{value:+.2f}"))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    save_figure("00_pnl_sanity_check")


def run_scenarios(make_plot: bool = True):
    """运行全部手算场景，默认同时生成盈亏曲线。"""
    results = []
    for config in SCENARIOS:
        result = run_scenario(config)
        results.append(result)
        print(
            f"{result['label']}: "
            f"gross_pnl={result['gross_pnl']:.5f}, "
            f"fees={result['fees']:.5f}, "
            f"expected_pnl={result['net_pnl']:.5f}, "
            f"actual_pnl={result['actual_pnl']:.5f}"
        )
        print(f"final_equity={result['final_equity']:.5f}")

    if make_plot:
        plot_pnl_curves(results)
    return results


if __name__ == "__main__":
    run_scenarios()
