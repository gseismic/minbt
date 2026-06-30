import builtins

import pytest

from minbt import Broker, Strategy


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


def test_strategy_broker_protocol_error_lists_target_methods():
    class OldStyleBroker:
        def submit_market_order(self, *args, **kwargs):
            return True

        def get_position_size(self, *args, **kwargs):
            return 0

        def get_position_sizes(self, *args, **kwargs):
            return {}

        def get_total_equity(self):
            return 0

        def get_equity(self, *args, **kwargs):
            return 0

        def get_cash(self, *args, **kwargs):
            return 0

        def get_positions(self, *args, **kwargs):
            return {}

    with pytest.raises(TypeError) as exc_info:
        Strategy(strategy_id="test", broker=OldStyleBroker())

    message = str(exc_info.value)
    assert "submit_limit_order" in message
    assert "order_target_percent" in message
    assert "close_position" in message


def test_strategy_exposes_only_new_data_callbacks():
    strategy = Strategy(strategy_id="test")

    assert hasattr(strategy, "on_bars")
    assert hasattr(strategy, "on_books")
    assert hasattr(strategy, "on_trades")
    assert hasattr(strategy, "on_news")
    assert not hasattr(strategy, "on_data")
    assert not hasattr(strategy, "on_bar")
