"""用策略类、JSON 参数和自己准备的数据运行，并从结果快照绘图。"""

from pathlib import Path

import matplotlib.pyplot as plt

from minbt import Bar, Strategy, run


# 用户自行准备的行；可以换成自己的文件、数据库或已读取的 DataFrame。
PREPARED_ROWS = [
    {"dt": "2026-01-01", "symbol": "TEST", "close": 100},
    {"dt": "2026-01-02", "symbol": "TEST", "close": 120},
]


class MyFeed:
    name = "prepared-data"

    def __init__(self, rows):
        self.rows = rows

    def events(self):
        for row in self.rows:
            yield Bar(row["dt"], row["symbol"], "kline", {"close": row["close"]})


def build_my_feeds(options):
    rows = [row for row in PREPARED_ROWS if row["symbol"] == options["symbol"]]
    return [MyFeed(rows)]


class BuyAndHold(Strategy):
    def on_bars(self, dt, bars):
        self.broker.order_target_size(self.params["symbol"], self.params["size"])


def run_strategy():
    config_path = Path(__file__).with_suffix(".json")
    result = run(BuyAndHold, config_path, feed_factory=build_my_feeds)
    curve = result.get_equity_curve()
    print(f"final_equity={curve[-1][1]:.2f}")
    print(f"net_pnl={result.get_total_pnl().net_pnl:.2f}")

    times = [dt for dt, equity in curve]
    equity = [value for dt, value in curve]
    net_pnl = [value - result.get_initial_cash() for value in equity]
    fig, axes = plt.subplots(2, 1, sharex=True)
    axes[0].plot(times, equity)
    axes[0].set_ylabel("Equity")
    axes[1].plot(times, net_pnl)
    axes[1].set_ylabel("Net PnL")
    fig.autofmt_xdate()
    plt.show()
    return result


if __name__ == "__main__":
    run_strategy()
