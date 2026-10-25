"""同一个固定增量策略用于回测与 Binance demo；默认只运行本地回测。"""

import argparse
import os

from minbt import Broker, Exchange, Strategy

SYMBOL = "BTCUSDT"
PARAMS = {"symbol": SYMBOL, "qty": 0.001}


class Pulse(Strategy):
    """信号变化时提交固定增量，示范接口复用，不实现目标仓位。"""

    def on_init(self):
        self.previous = None

    def on_bars(self, dt, bars):
        symbol = self.params["symbol"]
        bar = bars[symbol]
        rising = bar["close"] > bar["open"]
        if self.previous is not None and rising != self.previous:
            qty = self.params["qty"] if rising else -self.params["qty"]
            self.broker.submit_market_order(symbol, qty)
        self.previous = rising


def run_backtest():
    exchange = Exchange()
    exchange.set_bars([
        {"dt": "2026-10-01T00:01:00Z", "symbol": SYMBOL, "open": 60000, "close": 60100},
        {"dt": "2026-10-01T00:02:00Z", "symbol": SYMBOL, "open": 60100, "close": 60050},
        {"dt": "2026-10-01T00:03:00Z", "symbol": SYMBOL, "open": 60050, "close": 60000},
        {"dt": "2026-10-01T00:04:00Z", "symbol": SYMBOL, "open": 60000, "close": 60020},
    ])
    exchange.add_strategy(Pulse("pulse", broker=Broker(initial_cash=10000), params=PARAMS))
    return exchange.run()


def run_demo():
    from crypto_api.binance2 import usdm as binance2
    from minbt.plugins import binance

    with binance.Exchange(
        symbol=SYMBOL, interval="1m", environment="demo", sdk_factory=binance2.Exchange,
    ) as exchange:
        with binance2.Broker(
            os.environ["BINANCE_API_KEY"], os.environ["BINANCE_API_SECRET"],
            exchange=exchange.sdk,
        ) as account:
            exchange.add_strategy(Pulse("pulse", broker=binance.Broker(account), params=PARAMS))
            exchange.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=["backtest", "demo"], default="backtest")
    args = parser.parse_args()
    if args.mode == "demo":
        run_demo()
    else:
        import matplotlib.pyplot as plt

        result = run_backtest()
        curve = result.get_equity_curve()
        print(f"final_equity={curve[-1][1]:.2f}")
        plt.plot([dt for dt, _ in curve], [equity for _, equity in curve])
        plt.title("Pulse Backtest Equity")
        plt.show()
