from typing import Literal, Optional, Dict
import datetime
from .portfolio import Portfolio
from .struct import Position, DateType

class Monitor:
    def __init__(self):
        pass

class Broker:
    """
    交易经纪商
    
    一个Broker可以有多个Portfolio, 共享一个initial_cash
    多个Portfolio可以有不同的portfolio_cash，总和不能超过initial_cash
    """
    def __init__(self, 
                 initial_cash: float, 
                 fee_rate: float, 
                 *,
                 portfolio_cash: Optional[float] = None,
                 portfolio_id: str = 'default',
                 leverage: float = 1.0, 
                 margin_mode: Literal['cross', 'isolated'] = 'cross', 
                 warning_margin_level: float = 0.2, 
                 min_margin_level: float = 0.1):
        """
        Args:
        
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
        assert portfolio_cash is None or 0 < portfolio_cash < initial_cash, (
            f"portfolio_cash must be None or greater than 0 and less than initial_cash,"
            f"portfolio_cash: {portfolio_cash}, initial_cash: {initial_cash}"
        )

        self.fee_rate = fee_rate
        self.leverage = leverage
        self.margin_mode = margin_mode
        self.warning_margin_level = warning_margin_level
        self.min_margin_level = min_margin_level
        self.initial_cash = initial_cash
        self.remaining_free_cash = initial_cash
        self.portfolios = {}
        self.portfolio_id = portfolio_id
        portfolio_cash = portfolio_cash if portfolio_cash is not None else initial_cash
        self.add_sub_portfolio(portfolio_id=self.portfolio_id, initial_cash=portfolio_cash)
        
        self.monitor = Monitor()
        self.last_prices = {}
        self.last_price_dates = {}
    
    def add_sub_portfolio(self, portfolio_id: str, initial_cash: float) -> None:
        """
        占用 remaining_free_cash 的资金
        """
        assert 0 < initial_cash <= self.remaining_free_cash
        self.remaining_free_cash -= initial_cash
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
        # XXX: 假定没有locked_cash
        self.remaining_free_cash += portfolio.total_cash
    
    def on_new_price(self, symbol: str, price: float, dt: Optional[DateType] = None):
        self.last_prices[symbol] = price
        self.last_price_dates[symbol] = dt
        for portfolio in self.portfolios.values():
            portfolio.on_new_price(symbol, price, dt)
    
    def get_last_price(self, symbol: str, return_dt: bool = False) -> float:
        price = self.last_prices.get(symbol, None)
        if return_dt:
            return price, self.last_price_dates.get(symbol, None)
        else:
            return price
    
    def get_market_price(self, symbol: str, return_dt: bool = False) -> float:
        # 兼容测试
        return self.get_last_price(symbol, return_dt)
    
    def submit_market_order(self, 
                   symbol: str, 
                   qty: float, 
                   price: Optional[float] = None, 
                   leverage: Optional[float] = None, 
                   price_dt: Optional[DateType] = None,
                   portfolio_id: str = 'default'):
        """
        Arguments:
            last_price: 市价买入价格,也是市价卖出价格
        行为：
        1. 如果last_price为None，则使用last_prices中的价格
        2. 否则，使用传入的价格，并更新last_prices
        """
        # 注意，此时broker中的last_prices应已经通过on_new_price更新了
        if price is None:
            assert price_dt is None
            price, price_dt = self.get_last_price(symbol, return_dt=True)
        else:
            self.on_new_price(symbol, price, price_dt)
        if portfolio_id not in self.portfolios:
            raise ValueError(f"portfolio_id not found: {portfolio_id}")
        return self.portfolios[portfolio_id].submit_order(symbol, qty, price=price, leverage=leverage, price_dt=price_dt)
    
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
    
    def get_all_portfolio_equity(self) -> float:
        # 所有portfolio的权益总和
        return sum(portfolio.get_portfolio_equity() for portfolio in self.portfolios.values())
    
    def get_total_equity(self) -> float:
        return self.get_all_portfolio_equity() 
    
    def get_portfolio_equity(self, portfolio_id: Optional[str] = None) -> float:
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        return self.portfolios[portfolio_id].get_portfolio_equity()
    
    def get_portfolio_initial_cash(self, portfolio_id: Optional[str] = None) -> float:
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        return self.portfolios[portfolio_id].initial_cash
    
    def get_position(self, symbol: str, portfolio_id: Optional[str] = None) -> Position:
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        return self.portfolios[portfolio_id].get_position(symbol)
    
    def get_position_size(self, symbol: str, portfolio_id: Optional[str] = None) -> float:
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        return self.portfolios[portfolio_id].get_position_size(symbol)
    
    def get_position_sizes(self, portfolio_id: Optional[str] = None) -> Dict[str, float]:
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        portfolio = self.portfolios[portfolio_id]
        return {symbol: portfolio.get_position_size(symbol) for symbol in portfolio.get_positions().keys()}
    
    def get_positions(self, portfolio_id: Optional[str] = None) -> Dict[str, Position]:
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        return self.portfolios[portfolio_id].get_positions()
    
    def get_all_portfolio_positions(self) -> Dict[str, Dict[str, Position]]:
        return {portfolio_id: portfolio.get_positions() for portfolio_id, portfolio in self.portfolios.items()}
