from typing import Dict, Literal, Optional
from dataclasses import dataclass
from collections import defaultdict
from .logger import logger as default_logger

@dataclass
class StopOrder:
    price: float             # 触发价格
    qty: float              # 数量
    is_profit: bool         # True为止盈，False为止损
    triggered: bool = False  # 是否已触发

@dataclass
class PositionStats:
    position_size: float      
    gross_profit: float      
    pnl: float              
    fee: float              
    margin_level: float     
    liquidation_price: float 
    available_margin: float  
    allocated_margin: float  
    stop_orders: Dict[str, StopOrder]  # 新增：止盈止损订单

class PositionTracker:
    """仓位跟踪器：跟踪单个交易对的仓位状态、利润、费用等"""
    def __init__(self, fee_rate: float):
        self.fee_rate = fee_rate
        self.reset()
    
    def reset(self):
        self._position_size = 0
        self._last_price = None
        self._total_gross_profit = 0
        self._total_fee = 0
        self._total_pnl = 0
        self._stop_orders: Dict[str, StopOrder] = {}  # 新增：止盈止损订单
    
    def add_stop_order(self, order_id: str, price: float, qty: float, is_profit: bool) -> None:
        """添加止盈止损订单"""
        self._stop_orders[order_id] = StopOrder(price, qty, is_profit)
    
    def remove_stop_order(self, order_id: str) -> None:
        """移除止盈止损订单"""
        self._stop_orders.pop(order_id, None)
    
    def _check_stop_orders(self, price: float) -> Optional[StopOrder]:
        """检查是否触发止盈止损"""
        if not self._position_size:  # 没有持仓时不检查
            return None
            
        for order_id, stop_order in self._stop_orders.items():
            if stop_order.triggered:
                continue
                
            is_triggered = False
            if self._position_size > 0:  # 多仓
                if stop_order.is_profit and price >= stop_order.price:  # 止盈
                    is_triggered = True
                elif not stop_order.is_profit and price <= stop_order.price:  # 止损
                    is_triggered = True
            else:  # 空仓
                if stop_order.is_profit and price <= stop_order.price:  # 止盈
                    is_triggered = True
                elif not stop_order.is_profit and price >= stop_order.price:  # 止损
                    is_triggered = True
            
            if is_triggered:
                stop_order.triggered = True
                return stop_order
        
        return None
    
    def on_new_price(self, price: float):
        return self.on_new_trade(price, 0)
    
    def on_new_trade(self, price: float, qty: float, available_margin: float = 0):
        """
        处理新的交易或价格更新
        Args:
            price: 当前价格
            qty: 交易数量，正数买入，负数卖出
            available_margin: 可用保证金
        """
        new_position_size = self._position_size + qty
        new_fee = price * abs(qty) * self.fee_rate
        
        if self._last_price is not None:
            new_gross_profit = self._position_size * (price - self._last_price)
        else:
            new_gross_profit = 0

        self._total_gross_profit += new_gross_profit
        self._total_fee += new_fee
        self._total_pnl = self._total_gross_profit - self._total_fee
        
        position_value = abs(new_position_size * price)
        margin_level = available_margin / position_value if position_value > 0 else float('inf')
        
        if new_position_size != 0:
            maintenance_margin = available_margin * 0.05
            liquidation_price = price * (1 - margin_level + maintenance_margin) if new_position_size > 0 else \
                              price * (1 + margin_level - maintenance_margin)
        else:
            liquidation_price = 0

        self._position_size = new_position_size
        self._last_price = price
        
        # 返回时包含止盈止损订单信息
        return PositionStats(
            position_size=new_position_size,
            gross_profit=self._total_gross_profit,
            pnl=self._total_pnl,
            fee=self._total_fee,
            margin_level=margin_level,
            liquidation_price=liquidation_price,
            available_margin=available_margin,
            allocated_margin=0,
            stop_orders={k: v for k, v in self._stop_orders.items() if not v.triggered}
        )

class Broker:
    def __init__(self, 
                 initial_cash: float,
                 fee_rate: float,
                 leverage: float = 1.0,
                 margin_mode: Literal['cross', 'isolated'] = 'cross',  # cross=全仓, isolated=逐仓
                 logger=None):
        assert initial_cash > 0, 'initial_cash must be greater than 0'
        assert 0 <= fee_rate < 1, 'fee_rate must be between 0 and 1'
        assert leverage >= 1, 'leverage must be greater than or equal to 1'
        assert margin_mode in ['cross', 'isolated'], 'margin_mode must be either cross or isolated'
        
        self.initial_cash = initial_cash
        self.current_cash = initial_cash
        self.fee_rate = fee_rate
        self.leverage = leverage
        self.margin_mode = margin_mode
        self.logger = logger or default_logger
        self.positions: Dict[str, PositionStats] = {}
        self.position_trackers = defaultdict(lambda: PositionTracker(fee_rate))
        
        self.maintenance_margin_rate = 0.05
        self.initial_margin_rate = 0.1
        
        # 分仓模式下各个仓位的保证金
        self.allocated_margins: Dict[str, float] = defaultdict(float)
        
        self._stop_order_counter = 0  # 用于生成止盈止损订单ID
    
    def _generate_stop_order_id(self) -> str:
        """生成止盈止损订单ID"""
        self._stop_order_counter += 1
        return f"stop_{self._stop_order_counter}"
    
    def add_take_profit(self, symbol: str, price: float, qty: Optional[float] = None) -> str:
        """
        添加止盈订单
        Args:
            symbol: 交易对
            price: 触发价格
            qty: 平仓数量，None表示全部平仓
        Returns:
            str: 订单ID
        """
        position = self.get_position(symbol)
        if position.position_size == 0:
            self.logger.warning('no_position_for_tp', symbol)
            return ""
            
        qty = qty or abs(position.position_size)
        order_id = self._generate_stop_order_id()
        self.position_trackers[symbol].add_stop_order(order_id, price, qty, True)
        return order_id
    
    def add_stop_loss(self, symbol: str, price: float, qty: Optional[float] = None) -> str:
        """
        添加止损订单
        Args:
            symbol: 交易对
            price: 触发价格
            qty: 平仓数量，None表示全部平仓
        Returns:
            str: 订单ID
        """
        position = self.get_position(symbol)
        if position.position_size == 0:
            self.logger.warning('no_position_for_sl', symbol)
            return ""
            
        qty = qty or abs(position.position_size)
        order_id = self._generate_stop_order_id()
        self.position_trackers[symbol].add_stop_order(order_id, price, qty, False)
        return order_id
    
    def remove_stop_order(self, symbol: str, order_id: str):
        """移除止盈止损订单"""
        self.position_trackers[symbol].remove_stop_order(order_id)
    
    def _calculate_required_margin(self, symbol: str, price: float, qty: float) -> float:
        """计算所需保证金"""
        position = self.get_position(symbol)
        new_position_size = abs(position.position_size + qty)
        position_value = new_position_size * price
        return position_value * self.initial_margin_rate / self.leverage
        
    def _get_available_margin(self, symbol: str) -> float:
        """获取可用保证金"""
        if self.margin_mode == 'cross':
            # 全仓模式：可用全部资金
            return self.current_cash
        else:
            # 逐仓模式：只能使用分配给该仓位的资金
            return self.allocated_margins[symbol]
            
    def _check_margin(self, symbol: str, price: float, qty: float) -> bool:
        """检查保证金是否充足"""
        required_margin = self._calculate_required_margin(symbol, price, qty)
        available_margin = self._get_available_margin(symbol)
        return available_margin >= required_margin

    def _calculate_total_position_value(self) -> float:
        """计算所有仓位的总价值"""
        total_value = 0
        for symbol, position in self.positions.items():
            if position.position_size != 0:
                # 使用最新价格计算
                price = self.position_trackers[symbol]._last_price
                total_value += abs(position.position_size * price)
        return total_value

    def _check_cross_liquidation(self) -> bool:
        """检查全仓模式下是否触发爆仓"""
        total_position_value = self._calculate_total_position_value()
        if total_position_value == 0:
            return False
            
        total_margin_level = self.current_cash / total_position_value
        return total_margin_level <= self.maintenance_margin_rate

    def _check_isolated_liquidation(self, symbol: str, price: float) -> bool:
        """检查逐仓模式下是否触发爆仓"""
        position = self.get_position(symbol)
        if position.position_size == 0:
            return False
            
        allocated_margin = self.allocated_margins[symbol]
        position_value = abs(position.position_size * price)
        margin_level = allocated_margin / position_value
        return margin_level <= self.maintenance_margin_rate

    def _check_liquidation(self, symbol: str, price: float) -> bool:
        """检查是否触发爆仓"""
        if self.margin_mode == 'cross':
            return self._check_cross_liquidation()
        else:
            return self._check_isolated_liquidation(symbol, price)

    def allocate_margin(self, symbol: str, amount: float):
        """分配保证金到特定交易对（仅逐仓模式）"""
        if self.margin_mode != 'isolated':
            self.logger.warning('allocate_margin_ignored', 
                              'Margin allocation is only available in isolated mode')
            return
            
        if amount > self.current_cash:
            self.logger.error('insufficient_margin_for_allocation', amount, self.current_cash)
            return
            
        self.current_cash -= amount
        self.allocated_margins[symbol] += amount

    def get_position(self, symbol: str) -> PositionStats:
        return self.positions.get(symbol, PositionStats(0, 0, 0, 0, float('inf'), 0, self.current_cash, 0))

    def update_price(self, symbol: str, price: float):
        """更新价格并检查是否触发止盈止损或爆仓"""
        # 先检查止盈止损
        tracker = self.position_trackers[symbol]
        stop_order = tracker._check_stop_orders(price)
        if stop_order:
            position = self.get_position(symbol)
            if position.position_size > 0:
                self.sell(symbol, price, stop_order.qty, force=True)
                self.logger.info('stop_order_triggered', 
                               'take_profit' if stop_order.is_profit else 'stop_loss',
                               symbol, price, stop_order.qty)
            else:
                self.buy(symbol, price, stop_order.qty, force=True)
                self.logger.info('stop_order_triggered',
                               'take_profit' if stop_order.is_profit else 'stop_loss',
                               symbol, price, stop_order.qty)
            return
        
        # 检查爆仓
        if self._check_liquidation(symbol, price):
            self._handle_liquidation(symbol, price)
        else:
            available_margin = self._get_available_margin(symbol)
            position = tracker.on_new_trade(price, 0, available_margin)
            self.positions[symbol] = position

    def buy(self, symbol: str, price: float, qty: float, force: bool = False):
        if not force and not self._check_margin(symbol, price, qty):
            self.logger.error('insufficient_margin', symbol, qty, price)
            return self.get_position(symbol)

        fee = price * qty * self.fee_rate
        self.current_cash -= fee
        
        available_margin = self._get_available_margin(symbol)
        position = self.position_trackers[symbol].on_new_trade(
            price, qty, available_margin
        )
        self.positions[symbol] = position
        return position

    def sell(self, symbol: str, price: float, qty: float, force: bool = False):
        if not force and not self._check_margin(symbol, price, -qty):
            self.logger.error('insufficient_margin', symbol, -qty, price)
            return self.get_position(symbol)

        fee = price * qty * self.fee_rate
        self.current_cash -= fee
        
        available_margin = self._get_available_margin(symbol)
        position = self.position_trackers[symbol].on_new_trade(
            price, -qty, available_margin
        )
        self.positions[symbol] = position
        return position

    def available_margin(self) -> float:
        return self.current_cash

    def used_margin(self) -> float:
        total_used = 0
        for position in self.positions.values():
            if position.position_size != 0:
                total_used += abs(position.position_size * self._prev_price) * self.initial_margin_rate
        return total_used

    def margin_level(self) -> float:
        used_margin = self.used_margin()
        return self.current_cash / used_margin if used_margin > 0 else float('inf')
    