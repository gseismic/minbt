from typing import Literal, Optional, Dict
from .portfolio import Portfolio
from .struct import Position

class Monitor:
    def __init__(self):
        pass

class Broker:
    def __init__(self, 
                 initial_cash: float, 
                 fee_rate: float, 
                 leverage: float = 1.0, 
                 margin_mode: Literal['cross', 'isolated'] = 'cross', 
                 warning_margin_level: float = 0.2, 
                 min_margin_level: float = 0.1):
        """
        初始化Broker
        """
        assert 0 < fee_rate <= 1.0, (
            f"fee_rate must be between 0 and 1.0,"
            f"fee_rate: {fee_rate}"
        )
        assert leverage >= 1.0, (
            f"leverage must be greater than or equal to 1.0,"
            f"leverage: {leverage}"
        )
        assert warning_margin_level >= min_margin_level, (
            f"warning_margin_level must be greater than or equal to min_margin_level,"
            f"warning_margin_level: {warning_margin_level}, min_margin_level: {min_margin_level}"
        )
        assert 0 <= warning_margin_level <= 1.0, (
            f"warning_margin_level must be between 0 and 1.0,"
            f"warning_margin_level: {warning_margin_level}"
        )
        assert 0 <= min_margin_level <= 1.0, (
            f"min_margin_level must be between 0 and 1.0,"
            f"min_margin_level: {min_margin_level}"
        )
        self.fee_rate = fee_rate
        self.leverage = leverage
        self.margin_mode = margin_mode
        self.warning_margin_level = warning_margin_level
        self.min_margin_level = min_margin_level
        self.portfolios = {}
        self.monitor = Monitor()
        self.last_prices = {}
        self.add_portfolio(portfolio_id='default', initial_cash=initial_cash)
    
    def add_portfolio(self, portfolio_id: str, initial_cash: float) -> None:
        # 不占用 self.initial_cash的资金
        self.portfolios[portfolio_id] = Portfolio(
            initial_cash, 
            fee_rate=self.fee_rate, 
            leverage=self.leverage, 
            margin_mode=self.margin_mode, 
            warning_margin_level=self.warning_margin_level, 
            min_margin_level=self.min_margin_level
        )
    
    def close_portfolio(self, portfolio_id: str):
        portfolio = self.portfolios.pop(portfolio_id)
        portfolio.close_all_positions(self.last_prices)
    
    def on_new_price(self, symbol: str, price: float):
        self.last_prices[symbol] = price
        for portfolio in self.portfolios.values():
            portfolio.on_new_price(symbol, price)
    
    def get_market_price(self, symbol: str) -> float:
        return self.last_prices.get(symbol, None)
    
    def submit_market_order(self, 
                   symbol: str, 
                   qty: float, 
                   price: Optional[float] = None, 
                   leverage: Optional[float] = None, 
                   portfolio_id: str = 'default'):
        """
        Arguments:
            market_price: 市价买入价格,也是市价卖出价格
        行为：
        1. 如果market_price为None，则使用last_prices中的价格
        2. 否则，使用传入的价格，并更新last_prices
        """
        if price is None:
            price = self.get_market_price(symbol)
        else:
            self.on_new_price(symbol, price)
        if portfolio_id not in self.portfolios:
            raise ValueError(f"portfolio_id not found: {portfolio_id}")
        return self.portfolios[portfolio_id].submit_order(symbol, qty, price=price, leverage=leverage)
    
    def submit_limit_order(self, 
                  symbol: str, 
                  qty: float, 
                  price: float, 
                  tp_price: Optional[float] = None, 
                  sl_price: Optional[float] = None, 
                  leverage: Optional[float] = None, 
                  portfolio_id: str = 'default'):
        raise NotImplementedError()

    def cancel_order(self, symbol: str, order_id: str, portfolio_id: str = 'default'):
        # if portfolio_id not in self.portfolios:
        #     raise ValueError(f"portfolio_id not found: {portfolio_id}")
        # return self.portfolios[portfolio_id].cancel_order(symbol, order_id)
        raise NotImplementedError()
    
    def submit_stop_order(self,
                 symbol: str,
                 qty: float,
                 stop_price: float,
                 tp_price: Optional[float] = None,
                 sl_price: Optional[float] = None,
                 leverage: Optional[float] = None,
                 portfolio_id: str = 'default'):
        """
        下止损买入单(Stop Buy)
        当价格上涨超过stop_price时触发市价买入
        """
        raise NotImplementedError()

    def submit_trailing_stop_order(self,
                         symbol: str,
                         qty: float,
                         stop_distance: float,
                         tp_price: Optional[float] = None,
                         sl_price: Optional[float] = None,
                         leverage: Optional[float] = None,
                         portfolio_id: str = 'default'):
        """
        下追踪止损买入单
        stop_distance: 追踪止损距离，价格与最低点的距离超过此值时触发买入
        """
        raise NotImplementedError()

    def get_total_equity(self) -> float:
        return sum(portfolio.get_portfolio_equity() for portfolio in self.portfolios.values())
    
    def get_total_initial_cash(self) -> float:
        return sum(portfolio.initial_cash for portfolio in self.portfolios.values())
    
    def get_position(self, symbol: str, portfolio_id: str = 'default') -> Position:
        return self.portfolios[portfolio_id].get_position(symbol)
    
    def get_positions(self, portfolio_id: str = 'default') -> Dict[str, Position]:
        return self.portfolios[portfolio_id].get_positions()
