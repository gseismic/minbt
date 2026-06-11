from typing import Dict, Literal, Optional, Tuple, Union
import copy
import numpy as np
from ..logger import logger as default_logger
from .struct import Position, Cash, DateType

class Portfolio:
    
    def __init__(self, 
                 initial_cash: float,
                 fee_rate: float,
                 leverage: float = 1.0,
                 margin_mode: Literal['cross', 'isolated'] = 'cross',
                 warning_margin_level: float = 0.2,
                 min_margin_level: float = 0.1 ,
                 logger=None):
        """
        初始化Portfolio
        
        Args:
            initial_cash: 初始现金, >0
            fee_rate: 手续费率, 0 <= fee_rate < 1
            leverage: 杠杆倍数, >=1.0
            margin_mode: 保证金模式, cross[全仓]或isolated[逐仓]
            warning_margin_level: 警告保证金水平, 0-1
            min_margin_level: 最小保证金水平, 0-1s
        """
        assert initial_cash > 0, f'initial_cash must be greater than 0, got {initial_cash}'
        assert 0 <= fee_rate < 1, f'fee_rate must be between 0 and 1, got {fee_rate}'
        assert leverage >= 1, f'leverage must be greater than or equal to 1, got {leverage}'
        assert margin_mode in ['cross', 'isolated'], f'margin_mode must be either cross or isolated, got {margin_mode}'
        assert 0 <= min_margin_level < 1, f'min_margin_level must be between 0 and 1, got {min_margin_level}'
        assert 0 <= warning_margin_level < 1, f'warning_margin_level must be between 0 and 1, got {warning_margin_level}'
        assert min_margin_level < warning_margin_level, f'min_margin_level must be less than warning_margin_level, got {min_margin_level=} and {warning_margin_level=}'
        self.initial_cash = initial_cash
        self.fee_rate = fee_rate
        self.leverage = leverage
        self.margin_mode = margin_mode
        self.warning_margin_level = warning_margin_level
        self.min_margin_level = min_margin_level
        self.logger = logger or default_logger
        self.reset()
            
    def reset(self):
        self.last_prices = {}
        self.last_prices_dt = {}
        self._bankrupt = False
        self._current_cash = Cash(self.initial_cash, self.initial_cash)
        self._positions: Dict[str, Position] = {}
    
    def mark_bankrupt(self) -> None:
        self._bankrupt = True
        self._positions.clear()
        
    def get_all_positions_total_margin(self) -> float:
        return sum(position.margin for position in self._positions.values())
    
    def get_all_positions_total_equity(self) -> float:
        return sum(position.equity for position in self._positions.values())

    def get_portfolio_margin_level(self) -> float:
        if self._bankrupt:
            return -1.0
        total_margin = self.get_all_positions_total_margin()
        equity = self.get_all_positions_total_equity()
        if total_margin == 0:
            if equity == 0:
                return 1.0
            else:
                return 0.0
        return equity / total_margin

    def get_portfolio_equity(self) -> float:
        return self.get_all_positions_total_equity() + self.total_cash
    
    def on_new_price(self, 
                     symbol: str, 
                     price: float, 
                     dt: Optional[DateType] = None) -> Tuple[bool, bool, float]:
        """
        更新价格，更新各仓位的未实现盈亏，并检查保证金水平
        
        Args:
            symbol: 标的代码
            price: 最新价格
        
        Returns:
            bankrupt: 是否穿仓
                当为逐仓模式时，指的是单个仓位穿仓，不会导致账户破产
                当为全仓模式时，指的是账户穿仓，会导致账户破产
            liquidated: 是否达到强平水平
            margin_level: 保证金水平
        """
        if self._bankrupt:
            return True, False, 0.0
        
        liquidated, bankrupt = False, False
        self.last_prices[symbol] = price
        self.last_prices_dt[symbol] = dt
        margin_level = self._update_pnl_get_margin_level(symbol, price, dt)
        if margin_level < 0:
            bankrupt, liquidated = True, True
            self.logger.error(f'[{self.margin_mode}] {symbol} bankrupt, margin_level: {margin_level}')
            if self.margin_mode == 'isolated':
                position = self.get_position(symbol)
                position.mark_bankrupt()
                assert position.size == 0
            else:
                self.mark_bankrupt()
        elif margin_level <= self.min_margin_level:
            liquidated = True
            if self.margin_mode == 'isolated':
                self.logger.warning(f'[{self.margin_mode}] {symbol} reach liquidation, margin_level: {margin_level}')
                self._pure_close_position(symbol) # price 已经在_update_pnl_get_margin_level更新过了
                assert self.get_position(symbol).size == 0, f'{symbol} is not closed'
            else:
                self.logger.warning(f'[{self.margin_mode}] Reach liquidation, close all positions')
                self._pure_close_all_positions()
                assert self.get_all_positions_total_equity() == 0, f'All positions are not closed'
        elif margin_level <= self.warning_margin_level:
            self.logger.warning(f'[{self.margin_mode}] margin level is too low, margin_level: {margin_level}')

        return bankrupt, liquidated, margin_level
    
    def _update_pnl_get_margin_level(self, 
                                     symbol: str, 
                                     last_price: float, 
                                     dt: Optional[DateType] = None) -> float:
        """
        更新最小仓位收益并获取保证金水平
        
        Args:
            symbol: 标的代码
            last_price: 最新价格
        
        Returns:
            margin_level: 保证金水平
        """
        position = self.get_position(symbol, create_if_missing=False)
        if position is None:
            return self.get_portfolio_margin_level() if self.margin_mode == 'cross' else 1.0
        position.update_price_and_pnl(last_price, dt)
        if self.margin_mode == 'isolated':
            margin_level = position.margin_level
        else:
            margin_level = self.get_portfolio_margin_level()
        return margin_level

    def submit_order(self, symbol: str, qty: float, price: float, leverage: Optional[float] = None, price_dt: Optional[DateType] = None) -> bool:
        """提交订单
        
        Args:
            symbol: 标的代码
            qty: 数量，可正可负
            price: 价格
            leverage: 杠杆倍数，如果为None，使用默认杠杆
        
        依次进行:
            1. 更新价格，检查保证金水平，是否触发强制平仓
            2. 计算新开仓所需保证金和手续费，检查是否充足
            3. 提交订单，更新仓位和现金
        """
        if self._bankrupt:
            self.logger.error(f'Portfolio bankrupt, cannot submit order')
            return False
        
        if leverage is None:
            leverage = self.leverage
        
        # 更新价格并检查保证金（可能触发强平）
        bankrupt, liquidated, _ = self.on_new_price(symbol, price, price_dt)
        if bankrupt or liquidated:
            return False

        if qty == 0:
            self.logger.warning(f'Submit order with qty=0, symbol: {symbol}, leverage: {leverage}, qty: {qty}, price: {price}')
            return False

        # 检查保证金是否充足
        position = self.get_position(symbol)
        required_fee = self.calculate_fee(symbol, leverage, qty, price)
        
        fake_position = copy.deepcopy(position)
        exec_type, fake_released_margin, fake_realized_pnl = fake_position.commit_order(price, qty=qty, leverage=leverage)
        fake_released_cash = fake_released_margin + fake_realized_pnl - required_fee # 将释放的free_cash
        should_remaining_cash = self.free_cash + fake_released_cash # 额外需要的free_cash
        if should_remaining_cash < 0:
            self.logger.error(
                f"Insufficient free cash to open position({symbol}, qty={qty}, price={price}). "
                f"Required free cash: {-fake_released_cash}, Free cash: {self.free_cash}"
            )
            return False
        
        # 提交订单
        new_position_size = position.size + qty
        exec_type, released_margin, realized_pnl = position.commit_order(price, qty=qty, leverage=leverage)
        self.logger.info(f'Submit order: {symbol}, qty={qty}, price={price}, exec_type={exec_type}, fee={required_fee}')
        released_cash = released_margin + realized_pnl - required_fee
        
        # 前面已经考虑穿仓了，这里不会报错
        self._current_cash.change_cash(released_cash)
        
        self.logger.debug(
            f'Submit order: {symbol}, qty={qty}, price={price}, new_position_size={new_position_size}, '
            f'released_cash={released_cash}, realized_pnl={realized_pnl}'
        )
        return True
    
    def close_position(self, symbol: str, last_price: Optional[float] = None) -> bool:
        """平仓: 提交与当前持仓方向相反、数量相同的订单"""
        position = self.get_position(symbol)
        if position.is_empty():
            self.logger.warning(f'Cannot close empty position: {symbol}')
            return False
        if last_price is None:
            last_price = self.last_prices.get(symbol, position.last_price)
        if last_price is None:
            self.logger.error(f'Cannot close position {symbol}: no price available')
            return False
        return self.submit_order(symbol, -position.size, price=last_price)
    
    def close_all_positions(self, last_prices: Optional[Dict[str, float]] = None) -> None:
        for symbol in list(self._positions.keys()):
            position = self._positions.get(symbol)
            if position is None or position.is_empty():
                continue
            if last_prices is None:
                self.close_position(symbol)
            else:
                self.close_position(symbol, last_prices.get(symbol))
        assert np.allclose(self.get_all_positions_total_equity(), 0), f'All positions are not closed'
        assert np.allclose(self.get_portfolio_equity(), self.total_cash), f'Portfolio equity is not equal to total cash'

    def _pure_close_position(self, symbol: str, last_price: Optional[float] = None) -> Optional[Position]:
        if symbol not in self._positions:
            return None
        position = self._positions[symbol]
        released_margin, realized_pnl = position.commit_close_all(last_price)
        released_cash = released_margin + realized_pnl
        assert self._current_cash.can_change_cash(released_cash)
        self._current_cash.change_cash(released_cash)
        return position
    
    def _pure_close_all_positions(self, last_prices: Optional[Dict[str, float]] = None) -> None:
        """
        要求已经检查过保证金水平，不会穿仓
        """
        for symbol in self._positions.keys():
            if last_prices is None:
                self._pure_close_position(symbol)
            else:
                self._pure_close_position(symbol, last_prices.get(symbol))
    
    def get_position(self, symbol: str, create_if_missing: bool = True) -> Optional[Position]:
        if symbol not in self._positions:
            if not create_if_missing:
                return None
            self._positions[symbol] = Position(symbol=symbol)
        return self._positions[symbol]
    
    def get_position_size(self, symbol: str) -> float:
        return self.get_position(symbol).size
    
    def get_positions(self) -> Dict[str, Position]:
        return self._positions
    
    def get_position_sizes(self) -> Dict[str, float]:
        return {symbol: pos.size for symbol, pos in self._positions.items() if not pos.is_empty()}
    
    def get_total_cash(self) -> float:
        return self._current_cash.total_cash
    
    def get_cash(self, include_locked: bool = False) -> float:
        if include_locked:
            return self.total_cash
        else:
            return self.free_cash
    
    def get_free_cash(self) -> float:
        return self._current_cash.free_cash
    
    def get_locked_cash(self) -> float:
        return self._current_cash.locked_cash
    
    def get_equity(self) -> float:
        return self.get_portfolio_equity()
    
    def get_position_equity(self, symbol: str) -> float:
        return self.get_position(symbol).equity
    
    def calculate_fee(self, symbol: str, leverage: float, qty: float, price: float) -> float:
        """计算手续费"""
        return abs(qty) * price * self.fee_rate
    
    @property
    def cash(self) -> float:
        return self._current_cash.total_cash
    
    @property
    def free_cash(self) -> float:
        return self._current_cash.free_cash
    
    @property
    def locked_cash(self) -> float:
        return self._current_cash.locked_cash
    
    @property
    def total_cash(self) -> float:
        return self._current_cash.total_cash
    
    @property
    def positions(self) -> Dict[str, Position]:
        return self._positions

    @property
    def bankrupt(self) -> bool:
        return self._bankrupt
