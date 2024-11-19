from typing import Optional
from .broker import Broker
from .logger import logger as default_logger
from pyta_dev.utils.vector import NumpyVector, VectorTable

class Strategy:
    def __init__(self, 
                 strategy_id: str, 
                 broker: Optional[Broker]=None, 
                 params: dict={}, 
                 logger=None):
        """
        Args:
            strategy_id: 策略ID
            broker: 交易代理
            params: 参数
            logger: 日志记录器
        """
        self.strategy_id = strategy_id
        self.set_broker(broker)
        self.params = params
        self.logger = logger or default_logger
        self._equity_history = NumpyVector()
        self._position_size_history = VectorTable()
        
    def set_broker(self, broker: Broker):
        assert hasattr(broker, 'submit_market_order')
        assert hasattr(broker, 'get_position_size')
        assert hasattr(broker, 'get_total_equity')
        self.broker = broker
        
    def set_params(self, params: dict):
        self.params = params
    
    def update_params(self, **kwargs):
        self.params.update(kwargs)
        
    def set_exchange(self, exchange):
        self.exchange = exchange
    
    def on_init(self):
        pass
    
    def _on_exchange_data(self, data):
        self.on_data(data)
        
        # update equity and position size history
        equity = self.broker.get_total_equity()
        self._equity_history.append(equity)
        positions = self.broker.get_position_sizes()
        self._position_size_history.append(positions)

    def on_data(self, data):
        pass
    
    def on_finish(self):
        pass
    
    def get_hist_equity(self):
        return self._equity_history.to_numpy()
    
    def get_hist_position_sizes(self, symbol: str):
        return self._position_size_history.get_column(symbol)
    
    def get_broker_stats(self, portfolio_id: str = 'default'):
        return {
            'equity': self.broker.get_total_equity(portfolio_id),
            'cash': self.broker.get_cash(portfolio_id),
            'positions': self.broker.get_positions(portfolio_id)
        }
    
    def market_buy(self, symbol: str, qty: float):
        assert qty > 0
        return self.broker.submit_market_order(symbol, qty=qty)
    
    def market_sell(self, symbol: str, qty: float):
        return self.broker.market_sell(symbol, qty=qty)
    
    # def buy(self, symbol: str, price: float, qty: float):
    #     return self.broker.buy(symbol, price, qty)
    
    # def sell(self, symbol: str, price: float, qty: float):
    #     return self.broker.sell(symbol, price, qty)
    
    # def close_all(self):
    #     return self.broker.close_all()