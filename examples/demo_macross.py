from fintest.crypto.binance import api
from minbt import Exchange, Strategy, Broker
from pyta_dev.utils.plot import kplot_df, get_figax
from pyta_dev import rEMA
# from pyta_dev.utils.deque import NumpyDeque
from pyta_dev.utils.vector import NumpyVector

class TestStrategy(Strategy):
    
    def on_init(self):
        print('on_init')
        self.equity = []
        self.positions = []
        self.l1, self.l2 = 20, 50
        assert self.l1 < self.l2, 'l1 must be less than l2'
        self.fn_ema1 = rEMA(self.l1, buffer_size=int(1e6))
        self.fn_ema2 = rEMA(self.l2, buffer_size=int(1e6))
        self.closes = NumpyVector()
        
    def on_data(self, data):
        # print('on_data', dict(data))
        self.closes.append(data['close'])
        self.fn_ema1.rolling(self.closes)
        self.fn_ema2.rolling(self.closes)
        
        if self.fn_ema1.g_index > self.l2:
            if (
                self.fn_ema1.outputs['ma'][-1] > self.fn_ema2.outputs['ma'][-1] and
                self.fn_ema1.outputs['ma'][-2] < self.fn_ema2.outputs['ma'][-2]
            ):
                # 金叉买入
                self.broker.submit_market_order(symbol='BTCUSDT',
                                                qty=0.001, 
                                                price=data['close'],
                                                leverage=10)
            elif (
                self.fn_ema1.outputs['ma'][-1] < self.fn_ema2.outputs['ma'][-1] and
                self.fn_ema1.outputs['ma'][-2] > self.fn_ema2.outputs['ma'][-2]
            ):
                # 死叉卖出
                self.broker.submit_market_order(symbol='BTCUSDT',
                                                qty=-0.001, 
                                                price=data['close'],
                                                leverage=10)
        self.equity.append(self.broker.get_total_equity())
        self.positions.append(self.broker.get_position_size('BTCUSDT'))
    
    def on_finish(self):
        # print('on_finish', self.equity)
        print(len(self.fn_ema1.outputs), len(self.fn_ema2.outputs))
        from matplotlib import pyplot as plt
        fig, ax, *tx = get_figax(2)
        kplot_df(ax, self.exchange.data, show_volume=True)
        ax.plot(self.fn_ema1.outputs['ma'], label=f'ema1 {self.l1}')
        ax.plot(self.fn_ema2.outputs['ma'], label=f'ema2 {self.l2}')
        tx[0].plot(self.equity, color='green', label='equity')
        tx[1].plot(self.positions, color='blue', label='positions')
        tx[1].legend(loc='upper left')
        tx[0].legend(loc='upper right')
        plt.show()

def test_run_strategy():
    exchange = Exchange()
    data = api.get_future_klines_demo1(to_pandas=True)
    exchange.set_data(data[:600])
    # data[:600].to_csv('demo_data.csv')
    
    broker = Broker(initial_cash=10000, fee_rate=0.001)
    strategy = TestStrategy(strategy_id='test_strategy',
                            broker=broker)
    exchange.add_strategy(strategy)
    exchange.run()
    
    
if __name__ == '__main__':
    test_run_strategy()
