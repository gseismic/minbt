"""通过库级查询展示多头、空头和手续费场景的盈亏。"""

import matplotlib.pyplot as plt

from minbt import Broker, Exchange, Strategy


INITIAL_CASH = 1_000.0
SYMBOL = "TEST"
SCENARIOS = (
    ("long_profit", "多头盈利", (100.0, 110.0, 120.0), 1.0, 0.0),
    ("short_profit", "空头盈利", (100.0, 95.0, 90.0), -1.0, 0.0),
    ("fees_turn_small_gain_into_loss", "手续费覆盖小幅上涨", (100.0, 100.05), 1.0, 0.001),
)


class FixedTradeStrategy(Strategy):
    """在首根 bar 开仓、末根 bar 平仓，提供便于观察结果的最小交易场景。"""

    def __init__(self, strategy_id: str, broker: Broker, qty: float, exit_step: int):
        super().__init__(strategy_id=strategy_id, broker=broker)
        self.qty = qty  # 开仓数量，负数表示做空。
        self.exit_step = exit_step  # 最后一根 bar 的索引。
        self.step = 0  # 当前 bar 索引，用于安排开平仓。

    def on_bars(self, dt, bars):
        if self.step == 0:
            self.broker.submit_market_order(SYMBOL, qty=self.qty)
        elif self.step == self.exit_step:
            self.broker.close_position(SYMBOL)
        self.step += 1


def run_scenarios():
    """运行离线小场景，展示账户盈亏和订单记账明细。"""
    results = []
    for name, label, prices, qty, fee_rate in SCENARIOS:
        broker = Broker(initial_cash=INITIAL_CASH, fee_rate=fee_rate)
        strategy = FixedTradeStrategy(name, broker, qty, len(prices) - 1)
        exchange = Exchange()
        exchange.set_bars([
            {"dt": f"2026-01-{index + 1:02d}", "symbol": SYMBOL, "close": price}
            for index, price in enumerate(prices)
        ])
        exchange.add_strategy(strategy)
        exchange.run()

        pnl = broker.get_total_pnl()
        records = broker.get_pnl_records(symbol=SYMBOL)
        print(
            f"{label}: realized_pnl={pnl.realized_pnl:.5f}, "
            f"unrealized_pnl={pnl.unrealized_pnl:.5f}, "
            f"fees={pnl.fees:.5f}, net_pnl={pnl.net_pnl:.5f}"
        )
        print(f"final_equity={broker.get_total_equity():.5f}")
        for record in records:
            print(f"  order={record.order_id}, qty={record.qty:g}, net_pnl={record.net_pnl:.5f}")
        results.append({
            "name": name,
            "label": label,
            "pnl": pnl,
            "records": records,
            "pnl_curve": [equity - INITIAL_CASH for equity in strategy.get_hist_equity()],
            "final_equity": broker.get_total_equity(),
        })
    return results


if __name__ == "__main__":
    for result in run_scenarios():
        plt.plot(result["pnl_curve"], label=result["label"])
    plt.title("Scenario PnL")
    plt.axhline(0, color="black", linewidth=0.8)
    plt.legend()
    plt.show()
