import pandas as pd

from minbt import Exchange, Strategy, Broker, logger


class EmptyDataStrategy(Strategy):
    def on_init(self):
        self.initialized = True

    def on_finish(self):
        self.finished = True


def test_exchange_run_empty_data_does_not_divide_by_zero():
    """测试空行情数据仍可完成初始化和结束回调"""
    exchange = Exchange()
    strategy = EmptyDataStrategy(strategy_id='empty', broker=Broker(initial_cash=1000, fee_rate=0))
    data = pd.DataFrame(columns=['dt', 'symbol', 'close'])

    exchange.set_data(data, date_key='dt')
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.initialized
    assert strategy.finished
