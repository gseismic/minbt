"""仅用核心依赖和内联行情验证 minbt 安装及最小策略。"""

from minbt import Broker, Exchange, Strategy


class BuyAndHold(Strategy):
    """把目标持仓保持为一个单位，展示最少代码的买入并持有策略。"""

    def on_bars(self, dt, bars):
        self.broker.order_target_size("TEST", 1)


broker = Broker(initial_cash=1_000)
strategy = BuyAndHold("demo", broker=broker)
exchange = Exchange()
exchange.set_bars([
    {"dt": "2026-01-01", "symbol": "TEST", "close": 100},
    {"dt": "2026-01-02", "symbol": "TEST", "close": 120},
])
exchange.add_strategy(strategy)
result = exchange.run()
print(f"final_equity={broker.get_total_equity():.2f}")
