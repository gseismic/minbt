from minbt import Exchange, Strategy, Broker
from minbt.plot import get_figax
import matplotlib.pyplot as plt
import random

class DemoStrategy(Strategy):
    
    def on_init(self):
        self.logger.info('on_init')
        self.equity = []
        self.positions = []
        
    def on_data(self, data):
        self.logger.info('on_data', dict(data))
        self.broker.submit_market_order(symbol='BTCUSDT',
                                        qty=0.001*random.choice([-1, -1, -1, 1]),
                                        price=data['close'],
                                        leverage=10)
        
        self.equity.append(self.broker.get_total_equity())
        self.positions.append(self.broker.get_position_size('BTCUSDT'))
    
    def on_finish(self):
        fig, ax, *tx = get_figax(2)
        tx[0].plot(self.equity, color='green', lw=0.7, label='equity')
        tx[1].plot(self.positions, color='blue', lw=0.7, label='positions')
        tx[1].legend(loc='upper left')
        tx[0].legend(loc='upper right')
        plt.show()

def run_strategy():
    exchange = Exchange()
    import pandas as pd
    data = pd.read_csv('data.csv')
    exchange.set_data(data)
    
    broker = Broker(initial_cash=10000, fee_rate=0.001)
    strategy = DemoStrategy(strategy_id='test_strategy',
                            broker=broker)
    exchange.add_strategy(strategy)
    exchange.run()
    
    
if __name__ == '__main__':
    run_strategy()
