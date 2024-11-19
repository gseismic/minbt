import numpy as np
from dataclasses import dataclass
from typing import Optional, Union
from decimal import Decimal
import datetime

DateType = Union[datetime.datetime, np.datetime64]

class Cash:
    __slots__ = ['total_cash', 'free_cash', 'locked_cash']
    
    def __init__(self, total_cash: float, free_cash: float):
        assert total_cash >= 0, f"Cannot initialize total cash with negative value: {total_cash}"
        assert free_cash >= 0, f"Cannot initialize free cash with negative value: {free_cash}"
        assert total_cash >= free_cash, f"Total cash must be greater than free cash: {total_cash} < {free_cash}"
        self.total_cash = total_cash
        self.free_cash = free_cash
        self.locked_cash = total_cash - free_cash
    
    def add_cash(self, amount: float) -> None:
        """增加可用现金
        
        Args:
            amount: float 要增加的金额
        """
        assert amount >= 0, f"Cannot add negative cash: {amount}"
        self.free_cash += amount
        self.total_cash += amount
    
    def spend_cash(self, amount: float) -> None:
        """花费现金
        从可用现金中扣除指定金额，同时减少总现金
        
        Args:
            amount: float 要花费的金额
        """
        assert amount >= 0, f"Cannot spend negative amount: {amount}"
        assert amount <= self.free_cash, f"Cannot spend more than free cash: {amount} > {self.free_cash}"
        self.free_cash -= amount
        self.total_cash -= amount
    
    def can_change_cash(self, amount: float) -> bool:
        return self.free_cash + amount >= 0
    
    def change_cash(self, amount: float) -> None:
        """改变现金
        
        Args:
            amount: float 要改变的金额
        """
        if amount == 0:
            return
        
        new_free_cash = self.free_cash + amount
        assert new_free_cash >= 0, (
            f"Cannot change cash to negative: {new_free_cash}"
            f"amount: {amount}, free_cash: {self.free_cash}"
        )
        self.free_cash = new_free_cash
        self.total_cash += amount
    
    def lock_cash(self, amount: float) -> None:
        """锁定现金
        
        Args:
            amount: float 要锁定的金额
        """
        assert amount >= 0, f"Cannot lock negative cash: {amount}"
        assert amount <= self.free_cash, f"Cannot lock more cash than free: {amount} > {self.free_cash}"
        self.locked_cash += amount
        self.free_cash -= amount
    
    def unlock_cash(self, amount: float) -> None:
        """解锁现金
        
        Args:
            amount: float 要解锁的金额
        """
        assert amount >= 0, f"Cannot unlock negative cash: {amount}"
        assert amount <= self.locked_cash, f"Cannot unlock more cash than locked: {amount} > {self.locked_cash}"
        self.locked_cash -= amount
        self.free_cash += amount
    
    def __repr__(self) -> str:
        return f"Cash(total_cash={self.total_cash}, free_cash={self.free_cash}, locked_cash={self.locked_cash})"

@dataclass
class Position:
    """
    手续费从cash中扣除，不记录于_unrealized_pnl中
    
    Note: 因为可能是全仓或逐仓，所以这里不管理liquidation_price
    """
    symbol: str # primary key
    # leverage: float # primary key
    size: float = 0
    _cost_price: float = 0
    _margin: float = 0
    # 更新价格时自动计算
    _last_price: Optional[float] = None
    _last_dt: Optional[DateType] = None
    _unrealized_pnl: float = 0
    _equity: float = 0
    _bankrupt: bool = False
    
    def mark_bankrupt(self) -> None:
        self._bankrupt = True
        self.size = 0
        self._cost_price = 0
        self._margin = 0
        self._unrealized_pnl = 0
        self._equity = 0
    
    def update_price_and_pnl(self, price: float, dt: Optional[DateType] = None) -> None:
        if price is None:
            return
        assert price > 0, f"Price must be positive: {price}"
        self._last_price = price
        self._last_dt = dt
        self._unrealized_pnl = self.size * (price - self._cost_price)
        self._equity = self._unrealized_pnl + self._margin
    
    @staticmethod
    def calculate_required_margin(price: float, qty: float, leverage: float) -> float:
        assert price > 0, f"Price must be positive: {price}"
        assert leverage > 0, f"Leverage must be positive: {leverage}"
        return abs(qty) * price / leverage

    def commit_open_new(self, 
                        price: float, 
                        qty: float, 
                        leverage: float, 
                        dt: Optional[DateType] = None) -> tuple[float, float]:
        """在现有仓位基础上【同方向】新开仓
        Note:
            【调用本函数前】要求已经:
                - 检验过是否liquidation
                - 检查过保证金已经足够
        
        Return:
            released_margin: float 释放的保证金，占用保证金则为负
            realized_pnl: float 已实现pnl
            总释放现金为: released_margin + realized_pnl
        """
        assert np.sign(self.size * qty) >= 0, (
            "Cannot open new position with different sign: "
            f"position: {self.symbol}, size: {self.size}, qty: {qty}"
        )
        # 开仓关注cost_price, 不关心unrealized_pnl，所以不用更新价格
        new_size = self.size + qty
        if new_size == 0:
            # 此时: .size == qty == 0
            self._cost_price = 0
            self._margin = 0
        else:
            self._cost_price = (self._cost_price * self.size + qty * price) / new_size
            # 计算保证金占用
            extra_margin = self.calculate_required_margin(price, qty, leverage)
            self._margin += extra_margin
        self.size = new_size
        
        # 更新价格和pnl
        self.update_price_and_pnl(price, dt)
        
        released_margin = - extra_margin
        realized_pnl = 0
        return released_margin, realized_pnl
    
    def commit_close_partial(self, price: float, qty: float) -> tuple[float, float]:
        """在现有仓位基础上【同方向】平仓
            - 要求: 同方向
            - 要求: 平仓数量 <= 现有仓位数量
        Args:
            price: float 平仓价格
            qty: float 平仓数量, 可正可负
        Example:
            - .size == 100, qty == 20: 两者符号相同，报错
            - .size == 100, qty == -20: 部分平仓, 剩余仓位: 80
            - .size == 100, qty == -100: 全部平仓, 剩余仓位: 0
            - .size == 100, qty == -120: 超过仓位数量，报错
        Return:
            released_margin: float 释放的保证金
            realized_pnl: float 已实现pnl
            总释放现金为: released_margin + realized_pnl
        Note:
            手续费从cash中扣除，不记录于_unrealized_pnl中
        """
        assert np.sign(self.size * qty) <= 0, (
            "Cannot close partial position with different sign: "
            f"position: {self.symbol}, size: {self.size}, qty: {qty}"
        )
        assert abs(qty) <= abs(self.size), (
            f"Cannot close more than the position size: "
            f"position: {self.symbol}, size: {self.size}, qty: {qty}"
        )
        # 更新 _unrealized_pnl，这和开仓不同
        # 开仓时需要先更新价格，然后计算保证金占用
        # 平仓时需要先更新价格，然后计算已实现pnl
        self.update_price_and_pnl(price)
        
        if abs(qty) == abs(self.size):
            # 全部平仓
            released_margin = self._margin
            realized_pnl = self._unrealized_pnl
            self._margin = 0
            self._cost_price = 0
            self.size = 0
        else:
            ratio = abs(Decimal(str(qty)) / Decimal(str(self.size)))
            released_margin = Decimal(str(self._margin)) * ratio
            realized_pnl = Decimal(str(self._unrealized_pnl)) * ratio
            self._margin -= float(released_margin)
            self.size += qty
        # 更新价格和pnl
        self.update_price_and_pnl(price)
        return float(released_margin), float(realized_pnl)

    def commit_order(self, price: float, qty: float, leverage: float):
        order_type = np.sign(qty * self.size)
        released_margin, realized_pnl = 0, 0
        exec_type = None
        if order_type in [0, 1]:
            # 新开仓或同方向开仓
            exec_type = 'open_new'
            released_margin, realized_pnl = self.commit_open_new(price, qty, leverage=leverage)
        else:
            if abs(qty) <= abs(self.size):
                # 部分平仓
                exec_type = 'close_partial'
                released_margin, realized_pnl = self.commit_close_partial(price, qty)
            else:
                exec_type = 'close_new'
                # 全平仓
                old_size = self.size
                released_margin1, realized_pnl1 = self.commit_close_all(price)
                # 新开仓
                # remaining_qty = qty + self.size
                remaining_qty = qty + old_size # qty, old_size 符号相反
                released_margin2, realized_pnl2 = self.commit_open_new(price, remaining_qty, leverage=leverage)
                # sum up
                released_margin = released_margin1 + released_margin2
                realized_pnl = realized_pnl1 + realized_pnl2
        return exec_type, released_margin, realized_pnl

    
    def commit_close_all(self, last_price: Optional[float] = None) -> tuple[float, float]:
        if last_price is None:
            last_price = self._last_price
        return self.commit_close_partial(last_price, qty=-self.size)
    
    @property
    def unrealized_pnl(self) -> float:
        return self._unrealized_pnl
    
    @property
    def equity(self) -> float:
        return self._equity
    
    @property
    def side(self) -> str:
        """返回仓位方向: 'long', 'short' 或 'none'"""
        if self.size > 0:
            return 'long'
        elif self.size < 0:
            return 'short'
        return 'none'
    
    @property
    def margin_level(self) -> float:
        """返回保证金充足率
        
        保证金占总价值的比例，越高越安全
        """
        if self._margin == 0:
            assert self._equity == 0, f'Margin is 0, but equity is not 0: {self._equity}'
            return 1.0
        # equity = margin + unrealized_pnl，可能比margin大或小
        # 如果比margin大，说明在盈利，没有强平风险
        # 如果比margin小，说明在亏损，margin_level越小越危险
        # 1 + unrealized_pnl / margin
        # that is: self._equity/self._margin
        return self._equity / self._margin
    
    def is_empty(self) -> bool:
        return self.size == 0
    
    @property
    def cost_price(self) -> float:
        """返回开仓均价"""
        return self._cost_price
    
    @property
    def last_price(self) -> Optional[float]:
        """返回最新价格"""
        return self._last_price
    
    @property
    def margin(self) -> float:
        """返回保证金"""
        return self._margin
    
    # @property
    def current_leverage(self) -> float:
        """返回当前实际杠杆率"""
        if self._margin == 0:
            return 0
        return abs(self.size * self._last_price) / self._margin
    
    def __repr__(self) -> str:
        return (
            f"Position(symbol={self.symbol}, size={self.size}, "
            f"cost_price={self._cost_price}, "
            f"margin={self._margin}, unrealized_pnl={self._unrealized_pnl}, "
            f"equity={self._equity}, side={self.side}, last_price={self._last_price}, "
            f"margin_level={self.margin_level}, leverage={self.current_leverage()})"
        )
