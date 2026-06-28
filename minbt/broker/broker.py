from typing import Literal, Optional, Dict
from collections import defaultdict
from .portfolio import Portfolio
from .struct import Position, DateType, _require
from .market import MarketModel, SimpleMarket
from .exit import ExitRule, ExitContext
from ..logger import logger as default_logger

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
                 min_margin_level: float = 0.1,
                 market: Optional[MarketModel] = None,
                 logger=None):
        """
        Args:
        
        """
        _require(initial_cash > 0, f"initial_cash must be greater than 0, initial_cash: {initial_cash}")
        _require(
            0 <= fee_rate < 1.0,
            f"fee_rate must be between 0 (inclusive) and 1.0 (exclusive),"
            f"fee_rate: {fee_rate}",
        )
        _require(
            leverage >= 1.0,
            f"leverage must be greater than or equal to 1.0,"
            f"leverage: {leverage}",
        )
        _require(
            margin_mode in ['cross', 'isolated'],
            f"margin_mode must be either cross or isolated, margin_mode: {margin_mode}",
        )
        _require(
            0 <= min_margin_level < 1.0,
            f"min_margin_level must be between 0 (inclusive) and 1.0 (exclusive),"
            f"min_margin_level: {min_margin_level}",
        )
        _require(
            0 <= warning_margin_level < 1.0,
            f"warning_margin_level must be between 0 (inclusive) and 1.0 (exclusive),"
            f"warning_margin_level: {warning_margin_level}",
        )
        _require(
            min_margin_level < warning_margin_level,
            f"min_margin_level must be less than warning_margin_level,"
            f"warning_margin_level: {warning_margin_level}, min_margin_level: {min_margin_level}",
        )
        _require(
            portfolio_cash is None or 0 < portfolio_cash <= initial_cash,
            f"portfolio_cash must be None or greater than 0 and less than or equal to initial_cash,"
            f"portfolio_cash: {portfolio_cash}, initial_cash: {initial_cash}",
        )

        self.fee_rate = fee_rate
        self.leverage = leverage
        self.margin_mode = margin_mode
        self.warning_margin_level = warning_margin_level
        self.min_margin_level = min_margin_level
        self.market = market or SimpleMarket()
        self.logger = logger or default_logger
        self.initial_cash = initial_cash
        self.remaining_free_cash = initial_cash
        self.portfolios = {}
        self.portfolio_id = portfolio_id
        portfolio_cash = portfolio_cash if portfolio_cash is not None else initial_cash
        self.add_sub_portfolio(portfolio_id=self.portfolio_id, initial_cash=portfolio_cash)
        
        self.last_prices = {}
        self.last_price_dates = {}
        self._last_market_dt = None
        self._exit_rules = defaultdict(lambda: defaultdict(list))
    
    def add_sub_portfolio(self, portfolio_id: str, initial_cash: float) -> None:
        """
        占用 remaining_free_cash 的资金
        """
        if portfolio_id in self.portfolios:
            raise ValueError(f"portfolio_id already exists: {portfolio_id}")
        _require(
            0 < initial_cash <= self.remaining_free_cash,
            f"initial_cash must be greater than 0 and less than or equal to remaining_free_cash,"
            f" initial_cash: {initial_cash}, remaining_free_cash: {self.remaining_free_cash}",
        )
        self.remaining_free_cash -= initial_cash
        self.portfolios[portfolio_id] = Portfolio(
            initial_cash, 
            fee_rate=self.fee_rate, 
            leverage=self.leverage, 
            margin_mode=self.margin_mode, 
            warning_margin_level=self.warning_margin_level, 
            min_margin_level=self.min_margin_level,
            logger=self.logger,
        )
    
    def close_portfolio(self, portfolio_id: str):
        if portfolio_id not in self.portfolios:
            raise ValueError(f"portfolio_id not found: {portfolio_id}")
        portfolio = self.portfolios[portfolio_id]
        portfolio.close_all_positions(self.last_prices)
        self.portfolios.pop(portfolio_id)
        self.remaining_free_cash += portfolio.total_cash
    
    def on_new_price(self, symbol: str, price: float, dt: Optional[DateType] = None):
        _require(price > 0, f"price must be positive, price: {price}")
        if dt is not None and dt != self._last_market_dt:
            self.market.on_new_dt(self, dt)
            self._last_market_dt = dt
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
        if portfolio_id not in self.portfolios:
            raise ValueError(f"portfolio_id not found: {portfolio_id}")
        # 注意，此时broker中的last_prices应已经通过on_new_price更新了
        if price is None:
            if price_dt is not None:
                raise ValueError("price_dt must be None when price is omitted")
            price, price_dt = self.get_last_price(symbol, return_dt=True)
            if price is None:
                raise ValueError(f"market price not found: {symbol}")
        else:
            if price_dt is None:
                price_dt = self.last_price_dates.get(symbol)
            self.on_new_price(symbol, price, price_dt)
        validation = self.market.validate_order(self, symbol, qty, price, dt=price_dt, portfolio_id=portfolio_id)
        if not validation.ok:
            self.logger.warning(f"Order rejected: {symbol}, qty={qty}, price={price}, reason={validation.message}")
            return False
        result = self.portfolios[portfolio_id].submit_order(symbol, qty, price=price, leverage=leverage, price_dt=price_dt)
        if result:
            self.market.on_order_filled(self, symbol, qty, price, dt=price_dt, portfolio_id=portfolio_id)
        return result

    def order_target_size(
        self,
        symbol: str,
        target_size: float,
        price: Optional[float] = None,
        leverage: Optional[float] = None,
        price_dt: Optional[DateType] = None,
        portfolio_id: str = 'default',
    ) -> bool:
        current_size = self.get_position_size(symbol, portfolio_id=portfolio_id)
        qty = target_size - current_size
        if qty == 0:
            return False
        return self.submit_market_order(
            symbol,
            qty=qty,
            price=price,
            leverage=leverage,
            price_dt=price_dt,
            portfolio_id=portfolio_id,
        )

    def order_target_value(
        self,
        symbol: str,
        target_value: float,
        price: Optional[float] = None,
        leverage: Optional[float] = None,
        price_dt: Optional[DateType] = None,
        portfolio_id: str = 'default',
    ) -> bool:
        if price is None:
            price, price_dt = self.get_last_price(symbol, return_dt=True)
            if price is None:
                raise ValueError(f"market price not found: {symbol}")
        target_size = target_value / price
        return self.order_target_size(
            symbol,
            target_size=target_size,
            price=price,
            leverage=leverage,
            price_dt=price_dt,
            portfolio_id=portfolio_id,
        )

    def order_target_percent(
        self,
        symbol: str,
        target_percent: float,
        price: Optional[float] = None,
        leverage: Optional[float] = None,
        price_dt: Optional[DateType] = None,
        portfolio_id: str = 'default',
    ) -> bool:
        if price is not None:
            if price_dt is None:
                price_dt = self.last_price_dates.get(symbol)
            self.on_new_price(symbol, price, price_dt)
        equity = self.get_equity(portfolio_id=portfolio_id)
        target_value = equity * target_percent
        return self.order_target_value(
            symbol,
            target_value=target_value,
            price=price,
            leverage=leverage,
            price_dt=price_dt,
            portfolio_id=portfolio_id,
        )

    def close_position(
        self,
        symbol: str,
        price: Optional[float] = None,
        price_dt: Optional[DateType] = None,
        portfolio_id: str = 'default',
    ) -> bool:
        position = self.get_position(symbol, portfolio_id=portfolio_id, create_if_missing=False)
        if position is None or position.is_empty():
            self.logger.warning(f'Cannot close empty position: {symbol}')
            return False
        return self.submit_market_order(
            symbol,
            qty=-position.size,
            price=price,
            price_dt=price_dt,
            portfolio_id=portfolio_id,
        )

    def add_exit_rule(
        self,
        symbol: str,
        rule: Optional[ExitRule] = None,
        *,
        name: Optional[str] = None,
        condition=None,
        state=None,
        portfolio_id: str = 'default',
    ) -> ExitRule:
        if rule is not None and condition is not None:
            raise ValueError("rule and condition cannot both be provided")
        if rule is None:
            if condition is None:
                raise ValueError("either rule or condition must be provided")
            rule = ExitRule(name=name or getattr(condition, '__name__', 'exit_rule'), condition=condition, state=state)
        elif state is not None or name is not None:
            raise ValueError("name/state cannot be provided with rule")
        self._exit_rules[portfolio_id][symbol].append(rule)
        return rule

    def clear_exit_rules(self, symbol: Optional[str] = None, portfolio_id: Optional[str] = None) -> None:
        if portfolio_id is None:
            if symbol is None:
                self._exit_rules.clear()
                return
            for rules_by_symbol in self._exit_rules.values():
                rules_by_symbol.pop(symbol, None)
            return
        if symbol is None:
            self._exit_rules.pop(portfolio_id, None)
        else:
            self._exit_rules[portfolio_id].pop(symbol, None)

    def check_exit_rules(self, dt=None, data=None) -> None:
        for portfolio_id, rules_by_symbol in list(self._exit_rules.items()):
            if portfolio_id not in self.portfolios:
                continue
            for symbol, rules in list(rules_by_symbol.items()):
                position = self.get_position(symbol, portfolio_id=portfolio_id, create_if_missing=False)
                if position is None or position.is_empty():
                    continue
                price = self.get_last_price(symbol)
                if price is None:
                    continue
                for rule in list(rules):
                    ctx = ExitContext(
                        symbol=symbol,
                        dt=dt,
                        price=price,
                        position=position,
                        broker=self,
                        portfolio_id=portfolio_id,
                        data=data,
                        state=rule.get_state(),
                    )
                    if rule.condition(ctx):
                        ok = self.close_position(symbol, price=price, price_dt=dt, portfolio_id=portfolio_id)
                        if ok:
                            self.logger.info(f"Exit rule triggered: {rule.name}, symbol={symbol}, dt={dt}")
                        else:
                            self.logger.warning(f"Exit rule rejected: {rule.name}, symbol={symbol}, dt={dt}")
                        break
    
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
        return self.remaining_free_cash + self.get_all_portfolio_equity()
    
    def get_portfolio_equity(self, portfolio_id: Optional[str] = None) -> float:
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        return self.portfolios[portfolio_id].get_portfolio_equity()
    
    def get_portfolio_initial_cash(self, portfolio_id: Optional[str] = None) -> float:
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        return self.portfolios[portfolio_id].initial_cash
    
    # get 直接开头的，表示获取某个portfolio的值
    def get_equity(self, portfolio_id: Optional[str] = None) -> float:
        # 默认只返回主仓位
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        return self.portfolios[portfolio_id].get_portfolio_equity()
    
    def get_cash(self, include_locked: bool = False, portfolio_id: Optional[str] = None) -> float:
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        return self.portfolios[portfolio_id].get_cash(include_locked)

    def get_position(
        self,
        symbol: str,
        portfolio_id: Optional[str] = None,
        create_if_missing: bool = True,
    ) -> Optional[Position]:
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        return self.portfolios[portfolio_id].get_position(symbol, create_if_missing=create_if_missing)
    
    def get_position_size(self, symbol: str, portfolio_id: Optional[str] = None) -> float:
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        return self.portfolios[portfolio_id].get_position_size(symbol)
    
    def get_position_sizes(self, portfolio_id: Optional[str] = None) -> Dict[str, float]:
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        return self.portfolios[portfolio_id].get_position_sizes()
    
    def get_positions(self, portfolio_id: Optional[str] = None) -> Dict[str, Position]:
        if portfolio_id is None:
            portfolio_id = self.portfolio_id
        return self.portfolios[portfolio_id].get_positions()
