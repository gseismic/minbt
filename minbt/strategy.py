from typing import Optional
from .broker import Broker
from .logger import logger as default_logger

class Strategy:
    def __init__(self, 
                 strategy_id: str, 
                 broker: Optional[Broker]=None, 
                 config: dict={}, 
                 logger=None):
        self.strategy_id = strategy_id
        self.broker = broker
        self.config = config or {}
        self.logger = logger or default_logger
        
    def set_broker(self, broker: Broker):
        self.broker = broker
        
    def set_exchange(self, exchange):
        self.exchange = exchange
    
    def on_init(self):
        pass

    def on_data(self, data):
        pass
    
    def on_finish(self):
        pass
    
    # def market_buy(self, symbol: str, qty: float):
    #     price = self.exchange.get_price(symbol)
    #     return self.broker.market_buy(symbol, qty, price=price)
    
    # def market_sell(self, symbol: str, qty: float):
    #     price = self.exchange.get_price(symbol)
    #     return self.broker.market_sell(symbol, qty, price=price)
    
    # def buy(self, symbol: str, price: float, qty: float):
    #     return self.broker.buy(symbol, price, qty)
    
    # def sell(self, symbol: str, price: float, qty: float):
    #     return self.broker.sell(symbol, price, qty)
    
    # def close_all(self):
    #     return self.broker.close_all()