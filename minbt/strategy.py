from typing import Optional
from .broker import Broker
from .logger import logger as default_logger

class Strategy:
    def __init__(self, name, broker: Broker, config: dict={}, logger=None):
        self.name = name
        self.broker = broker
        self.config = config or {}
        self.logger = logger or default_logger
    
    def set_exchange(self, exchange):
        self.exchange = exchange
    
    def on_init(self):
        pass

    def on_data(self, data):
        pass
    
    def on_end(self):
        pass
    
    def market_buy(self, symbol: str, qty: float):
        market_price = self.exchange.get_price(symbol)
        return self.broker.market_buy(symbol, qty, market_price=market_price)
    
    def market_sell(self, symbol: str, qty: float):
        market_price = self.exchange.get_price(symbol)
        return self.broker.market_sell(symbol, qty, market_price=market_price)
    
    def buy(self, symbol: str, price: float, qty: float):
        return self.broker.buy(symbol, price, qty)
    
    def sell(self, symbol: str, price: float, qty: float):
        return self.broker.sell(symbol, price, qty)
    
    def close_all(self):
        return self.broker.close_all()