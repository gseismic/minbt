from typing import Literal

class Order:
    """
    订单状态机
    
    TODO:
        - 使用 Decimal 类型
    """
    
    def __init__(self, 
                 symbol: str, 
                 leverage: float, 
                 price: float, 
                 qty: float, 
                 side: Literal['buy', 'sell']):
        """
        创建一个订单
        
        Args:
            symbol: str 标的代码
            leverage: float 杠杆率，必须为正
            price: float 价格，必须为正
            qty: float 数量, 必须为正
        """
        assert leverage > 0, f"Leverage must be positive: {leverage}"
        assert price > 0, f"Price must be positive: {price}"
        assert symbol, "Symbol cannot be empty"
        assert qty > 0, f"Quantity must be positive: {qty}"
        self.symbol = symbol
        self.leverage = leverage
        self.price = price
        self.qty = qty
        self.side = side
        self.status = 'pending'
        self.fee = 0 # 已经花费的手续费
        self.filled_qty = 0 # 已经成交的数量
        self.unfilled_qty = qty # 未成交的数量
        self.last_price = None # 最新成交价格
    
    def fill(self, price: float, qty: float, fee: float, is_all):
        if self.is_filled():
            raise ValueError(f"Order already filled: {self}")
        assert qty > 0, f'Cannot fill negative quantity: {qty}'
        assert qty <= self.unfilled_qty, f'Cannot fill more than the unfilled quantity: {qty}, unfilled_qty: {self.unfilled_qty}'
        self.last_price = price
        self.fee += fee
        if is_all:
            self.status = 'filled'
            self.filled_qty = qty
            self.unfilled_qty = 0
        else:
            self.status = 'partially_filled'
            self.filled_qty += qty
            self.unfilled_qty -= qty
            if self.unfilled_qty == 0:
                self.status = 'filled'
    
    def fill_all(self, price: float, fee: float):
        self.fill(price, self.unfilled_qty, fee)
    
    def is_filled(self) -> bool:
        return self.status == 'filled'
    
    def is_partially_filled(self) -> bool:
        return self.status == 'partially_filled'
    
    def is_pending(self) -> bool:
        return self.status == 'pending'
