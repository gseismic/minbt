"""暂停策略但继续记录账户，随后继续执行并中途退出，绘制实际处理曲线。"""

from datetime import datetime, timedelta, timezone

import matplotlib.pyplot as plt

from minbt import Broker, Exchange, Strategy


class HoldStrategy(Strategy):
    """首次买入后保持仓位，展示暂停期间也存在真实账户收益。"""

    def on_init(self):
        self.calls = 0

    def on_bars(self, dt, bars):
        if self.calls == 0:
            self.broker.submit_market_order("BTCUSDT", qty=1)
        self.calls += 1


def run():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prices = (100, 105, 95, 110, 115, 999)
    data = [
        {"dt": start + timedelta(days=i), "symbol": "BTCUSDT", "close": price}
        for i, price in enumerate(prices)
    ]
    exchange = Exchange()
    exchange.set_bars(data)
    strategy = HoldStrategy("hold", Broker(initial_cash=1000))
    exchange.add_strategy(strategy)

    def control():
        # 读取上一完整批次的时间，历史控制可确定性重放。
        last = exchange.get_current_dt()
        if last is None:
            return "continue"
        if last >= start + timedelta(days=4):
            return "exit"
        if last < start + timedelta(days=2):
            return "pause"
        return "continue"

    result = exchange.run(control=control)
    curve = result.get_equity_curve()
    print(f"status={result.meta['status']} reason={result.meta['reason']}")
    print(f"step_count={result.meta['step_count']} strategy_callbacks={strategy.calls}")
    print(f"last_dt={result.meta['last_dt'].isoformat()}")
    print(f"final_equity={curve[-1][1]:.2f} net_pnl={result.get_total_pnl().net_pnl:.2f}")
    return result


if __name__ == "__main__":
    result = run()
    dates, equity = zip(*result.get_equity_curve())
    plt.plot(dates, equity)
    # 控制记录保存已完成步数，可据此标注真正暂停的采样区间。
    paused_from = None
    for _, steps, action in result.meta["control_events"]:
        if action == "pause":
            paused_from = steps
        elif paused_from is not None:
            plt.axvspan(dates[paused_from], dates[steps - 1], alpha=0.15, color="gray")
            paused_from = None
    plt.title(f"Run Control Equity ({result.meta['status']})")
    plt.xlabel("Time")
    plt.ylabel("Equity")
    plt.show()
