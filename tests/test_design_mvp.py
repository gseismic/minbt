import pandas as pd
import pytest

from minbt import (
    Broker,
    ChinaAStockMarket,
    Exchange,
    Strategy,
    stop_loss_pct,
)


class BarsOnlyStrategy(Strategy):
    def on_init(self):
        self.calls = []

    def on_bars(self, dt, bars):
        self.calls.append((dt, list(bars.keys()), bars["A"]["close"], bars["B"]["close"]))

    def on_data(self, data):
        raise AssertionError("on_data should not be called when on_bars is implemented")

    def on_bar(self, dt, rows_by_symbol):
        raise AssertionError("on_bar should not be called when on_bars is implemented")


def test_exchange_set_bars_prefers_on_bars():
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

    exchange.set_bars(data, date_key="dt")
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.calls == [
        ("2026-01-01", ["A", "B"], 100.0, 200.0),
        ("2026-01-02", ["A", "B"], 101.0, 201.0),
    ]


def test_broker_order_target_percent_and_size():
    broker = Broker(initial_cash=1000, fee_rate=0)

    assert broker.order_target_percent("BTCUSDT", 0.5, price=100)
    assert broker.get_position_size("BTCUSDT") == 5
    assert broker.get_cash() == 500

    assert broker.order_target_size("BTCUSDT", 2, price=100)
    assert broker.get_position_size("BTCUSDT") == 2
    assert broker.get_cash() == 800

    assert broker.order_target_value("BTCUSDT", 0, price=100)
    assert broker.get_position_size("BTCUSDT") == 0


def test_order_target_percent_uses_explicit_price_for_equity():
    broker = Broker(initial_cash=1000, fee_rate=0)

    assert broker.submit_market_order("BTCUSDT", qty=5, price=100)
    assert broker.order_target_percent("BTCUSDT", 0.5, price=200)

    assert broker.get_position_size("BTCUSDT") == pytest.approx(3.75)


def test_china_a_stock_market_locks_same_day_buy():
    broker = Broker(initial_cash=100000, fee_rate=0, market=ChinaAStockMarket())

    assert broker.submit_market_order("600519.SH", qty=100, price=100, price_dt="2026-01-05")
    position = broker.get_position("600519.SH")
    assert position.size == 100
    assert position.available_size == 0
    assert position.locked_size == 100

    assert not broker.close_position("600519.SH", price=99, price_dt="2026-01-05")
    assert broker.get_position_size("600519.SH") == 100

    broker.on_new_price("600519.SH", 101, "2026-01-06")
    assert position.available_size == 100
    assert position.locked_size == 0
    assert broker.close_position("600519.SH", price=101, price_dt="2026-01-06")
    assert broker.get_position_size("600519.SH") == 0


class StopLossStrategy(Strategy):
    def on_init(self):
        self.broker.add_exit_rule("BTCUSDT", stop_loss_pct(0.05))
        self.seen_positions = []

    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["close"]
        if dt == "2026-01-01":
            self.broker.submit_market_order("BTCUSDT", qty=1, price=price)
        self.seen_positions.append(self.broker.get_position_size("BTCUSDT"))


def test_exit_rule_runs_before_on_bars():
    exchange = Exchange()
    broker = Broker(initial_cash=1000, fee_rate=0)
    strategy = StopLossStrategy(strategy_id="stop", broker=broker)
    data = [
        {"dt": "2026-01-01", "symbol": "BTCUSDT", "close": 100.0},
        {"dt": "2026-01-02", "symbol": "BTCUSDT", "close": 94.0},
    ]

    exchange.set_bars(data, date_key="dt")
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.seen_positions == [1, 0]
    assert broker.get_position_size("BTCUSDT") == 0
