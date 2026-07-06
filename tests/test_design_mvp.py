from datetime import datetime, timezone

import pandas as pd

import minbt
from minbt import Broker, Exchange, Order, Strategy, markets


def _utc(year, month, day):
    return datetime(year, month, day, tzinfo=timezone.utc)


class BarsOnlyStrategy(Strategy):
    def on_init(self):
        self.calls = []

    def on_bars(self, dt, bars):
        self.calls.append((dt, list(bars.keys()), bars["A"]["close"], bars["B"]["close"]))


def test_exchange_set_bars_uses_only_on_bars():
    exchange = Exchange()
    strategy = BarsOnlyStrategy(strategy_id="bars")
    data = pd.DataFrame(
        [
            {"dt": "2026-01-01", "symbol": "A", "close": 100.0},
            {"dt": "2026-01-01", "symbol": "B", "close": 200.0},
            {"dt": "2026-01-02", "symbol": "A", "close": 101.0},
            {"dt": "2026-01-02", "symbol": "B", "close": 201.0},
        ]
    )

    exchange.set_bars(data)
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.calls == [
        (_utc(2026, 1, 1), ["A", "B"], 100.0, 200.0),
        (_utc(2026, 1, 2), ["A", "B"], 101.0, 201.0),
    ]


def test_old_user_interfaces_are_not_exported():
    assert not hasattr(Exchange, "set_data")
    assert not hasattr(Strategy, "on_data")
    assert not hasattr(Strategy, "on_bar")
    assert not hasattr(Broker, "add_sub_portfolio")
    assert not hasattr(minbt, "SimpleMarket")
    assert not hasattr(minbt, "CryptoMarket")
    assert not hasattr(minbt, "ChinaAStockMarket")
    assert not hasattr(minbt, "MarketModel")


def test_order_contract_has_stable_fields():
    broker = Broker(initial_cash=1000, fee_rate=0)

    order = broker.submit_market_order("AAPL", qty=1, price=100)

    assert isinstance(order, Order)
    assert order.id
    assert order.symbol == "AAPL"
    assert order.portfolio == "main"
    assert order.order_type == "market"
    assert order.source == "submit_market_order"
    assert order.side == "buy"
    assert order.qty == 1
    assert order.status == "filled"
    assert order.requested_price == 100
    assert order.limit_price is None
    assert order.filled_qty == 1
    assert order.avg_price == 100
    assert order.reason is None


class StopLossStrategy(Strategy):
    def on_init(self):
        self.seen_positions = []
        self.entry_order = None

    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["close"]
        if self.entry_order is None:
            self.entry_order = self.broker.submit_market_order(
                "BTCUSDT",
                qty=1,
                price=price,
                stop_loss_price=95,
            )
        self.seen_positions.append(self.broker.get_position_size("BTCUSDT"))


def test_order_exit_runs_before_on_bars():
    exchange = Exchange()
    broker = Broker(initial_cash=1000, fee_rate=0)
    strategy = StopLossStrategy(strategy_id="stop", broker=broker)
    data = [
        {"dt": "2026-01-01", "symbol": "BTCUSDT", "close": 100.0},
        {"dt": "2026-01-02", "symbol": "BTCUSDT", "close": 94.0},
    ]

    exchange.set_bars(data)
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.entry_order.status == "filled"
    assert strategy.seen_positions == [1, 0]
    assert broker.get_position_size("BTCUSDT") == 0


def test_market_is_defined_by_features_not_market_classes():
    assert markets.A_STOCK.name == "AStock"
    assert markets.A_STOCK.t_plus == 1
    assert markets.A_STOCK.lot_size == 100
    assert markets.CRYPTO.name == "Crypto"
    assert markets.CRYPTO.t_plus == 0
