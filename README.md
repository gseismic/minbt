# minbt

minbt 是一个简易的量化交易框架[代码量小于1000行]

## 主要特点
- [x] 支持【逐仓】和【全仓】两种保证金模式
- [x] 多空双向持仓
- [x] 支持动态杠杆
- [x] 支持市价单
- [x] 支持分仓
- [ ] 支持限价单
- [ ] 支持止盈止损

## 示例
[demo_mini.py](./examples/demo_mini.py)
```python
# python examples/demo_mini.py
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
        self.positions.append(self.broker.get_position('BTCUSDT').size)
    
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
```

## ChangeLog
- [@2024-11-16] v0.0.3 release
