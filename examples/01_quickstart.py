"""最小回测：买入一个单位并持有。"""

import matplotlib.pyplot as plt

from minbt import Broker, Exchange, Strategy


class BuyAndHold(Strategy):
    def on_bars(self, dt, bars):
        print(dt, bars)
        self.broker.order_target_size("TEST", 1)


broker = Broker(initial_cash=1_000)
strategy = BuyAndHold("demo", broker=broker)
exchange = Exchange()
exchange.set_bars([
    {"dt": "2026-01-01", "symbol": "TEST", "close": 100},
    {"dt": "2026-01-02", "symbol": "TEST", "close": 120},
])
exchange.add_strategy(strategy)
exchange.run()
print(f"final_equity={broker.get_total_equity():.2f}")
plt.plot(strategy.get_hist_equity())
plt.show()
