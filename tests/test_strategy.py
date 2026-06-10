import builtins

from minbt import Broker, Strategy


def test_strategy_history_without_pyta(monkeypatch):
    real_import = builtins.__import__

    def block_pyta(name, *args, **kwargs):
        if name.startswith('pyta_dev'):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', block_pyta)

    strategy = Strategy(strategy_id='test', broker=Broker(initial_cash=1000, fee_rate=0))
    strategy._on_exchange_data({'symbol': 'AAPL', 'close': 100})

    assert strategy.get_hist_equity() == [1000]
    assert strategy.get_hist_position_sizes('AAPL') == [0]


def test_strategy_without_broker_skips_broker_history():
    strategy = Strategy(strategy_id='test')
    strategy._on_exchange_data({'symbol': 'AAPL', 'close': 100})

    assert strategy.get_hist_equity() == []
    assert strategy.get_hist_position_sizes('AAPL') == []


def test_strategy_get_broker_stats_uses_requested_portfolio():
    broker = Broker(initial_cash=1000, fee_rate=0, portfolio_cash=600)
    broker.add_sub_portfolio('alt', 300)
    strategy = Strategy(strategy_id='test', broker=broker)

    stats = strategy.get_broker_stats(portfolio_id='alt')

    assert stats['equity'] == 300
    assert stats['cash'] == 300
    assert stats['positions'] == {}
