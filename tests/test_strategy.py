import builtins

import pytest

from minbt import Broker, Exchange, Strategy


def test_strategy_history_without_pyta(monkeypatch):
    real_import = builtins.__import__

    def block_pyta(name, *args, **kwargs):
        if name.startswith("pyta2"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_pyta)

    strategy = Strategy(strategy_id="test", broker=Broker(initial_cash=1000, fee_rate=0))
    strategy._record_broker_history()

    assert strategy.get_hist_equity() == [1000]
    assert strategy.get_hist_position_sizes("AAPL") == [0]
    assert isinstance(strategy.get_hist_equity(), list)
    assert isinstance(strategy.get_hist_position_sizes("AAPL"), list)


def test_strategy_history_with_pyta_has_stable_list_semantics():
    pytest.importorskip("pyta2")
    broker = Broker(initial_cash=1000, fee_rate=0)
    strategy = Strategy(strategy_id="test", broker=broker)

    strategy._record_broker_history()
    broker.submit_market_order("AAPL", qty=1, price=100)
    strategy._record_broker_history()
    broker.close_position("AAPL", price=100)
    strategy._record_broker_history()

    assert strategy.get_hist_equity() == [1000, 1000, 1000]
    assert strategy.get_hist_position_sizes("AAPL") == [0, 1, 0]
    assert strategy.get_hist_position_sizes("NEVER_TRADED") == [0, 0, 0]
    assert isinstance(strategy.get_hist_equity(), list)
    assert isinstance(strategy.get_hist_position_sizes("AAPL"), list)


def test_strategy_without_broker_skips_broker_history():
    strategy = Strategy(strategy_id="test")
    strategy._record_broker_history()

    assert strategy.get_hist_equity() == []
    assert strategy.get_hist_position_sizes("AAPL") == []


def test_strategy_get_broker_stats_uses_requested_portfolio():
    broker = Broker(initial_cash=1000, fee_rate=0)
    broker.add_portfolio("alt", cash=300)
    strategy = Strategy(strategy_id="test", broker=broker)

    stats = strategy.get_broker_stats(portfolio="alt")

    assert stats["equity"] == 300
    assert stats["cash"] == 300
    assert stats["positions"] == {}


def test_strategy_accepts_minimal_trading_broker_but_historical_run_rejects_it():
    class MinimalBroker:
        def submit_market_order(self, symbol, qty):
            return True

        def get_position_size(self, symbol):
            return 0

    broker = MinimalBroker()
    strategy = Strategy(strategy_id="test", broker=broker)
    assert strategy.broker is broker

    exchange = Exchange()
    exchange.set_bars([{"dt": "2026-01-01", "symbol": "BTCUSDT", "close": 100}])
    exchange.add_strategy(strategy)
    with pytest.raises(TypeError, match="historical Exchange requires ReplayBrokerProtocol"):
        exchange.run()


@pytest.mark.parametrize("missing", ["submit_market_order", "get_position_size"])
def test_strategy_broker_protocol_error_lists_minimal_methods(missing):
    methods = {
        "submit_market_order": lambda self, symbol, qty: True,
        "get_position_size": lambda self, symbol: 0,
    }
    methods.pop(missing)
    broker = type("IncompleteBroker", (), methods)()
    with pytest.raises(TypeError, match="TradingBrokerProtocol") as exc_info:
        Strategy(strategy_id="test", broker=broker)
    assert "submit_market_order" in str(exc_info.value)
    assert "get_position_size" in str(exc_info.value)


def test_strategy_exposes_only_new_data_callbacks():
    strategy = Strategy(strategy_id="test")

    assert hasattr(strategy, "on_bars")
    assert hasattr(strategy, "on_bar")
    assert hasattr(strategy, "on_books")
    assert hasattr(strategy, "on_trades")
    assert hasattr(strategy, "on_news")
    assert not hasattr(strategy, "on_data")
    assert not hasattr(strategy, "market_buy")
    assert not hasattr(strategy, "market_sell")
    assert not hasattr(strategy, "market_order")
