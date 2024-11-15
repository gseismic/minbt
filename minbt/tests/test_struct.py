import pytest
import numpy as np
from decimal import Decimal
from ..broker.struct import Cash, Position, Order

# Cash 测试部分保持不变...

def test_position_initialization():
    """测试 Position 类的初始化"""
    pos = Position(symbol="BTC-USDT", leverage=2.0)
    assert pos.symbol == "BTC-USDT"
    assert pos.leverage == 2.0
    assert pos.size == 0
    assert pos.cost_price == 0
    assert pos.margin == 0
    assert pos.last_price is None
    assert pos.unrealized_pnl == 0
    assert pos.equity == 0
    assert pos.is_empty()

def test_position_update_price():
    """测试价格更新功能"""
    pos = Position(symbol="BTC-USDT", leverage=2.0)
    pos.size = 1.0
    pos._cost_price = 50000.0
    pos._margin = 25000.0
    
    # 正常更新
    pos.update_price_and_pnl(51000.0)
    assert pos.last_price == 51000.0
    assert pos.unrealized_pnl == 1000.0
    assert pos.equity == 26000.0

    # 异常情况
    with pytest.raises(AssertionError):
        pos.update_price_and_pnl(-1000.0)
    with pytest.raises(AssertionError):
        pos.update_price_and_pnl(0)

def test_position_open_new():
    """测试开新仓位"""
    pos = Position(symbol="BTC-USDT", leverage=2.0)
    
    # 首次开仓
    released_margin, realized_pnl = pos.commit_open_new(price=50000.0, qty=1.0)
    assert released_margin == -25000.0  # 占用保证金
    assert realized_pnl == 0
    assert pos.size == 1.0
    assert pos.cost_price == 50000.0
    assert pos.margin == 25000.0
    
    # 同向加仓
    released_margin, realized_pnl = pos.commit_open_new(price=51000.0, qty=1.0)
    assert released_margin == -25500.0
    assert realized_pnl == 0
    assert pos.size == 2.0
    assert pos.cost_price == 50500.0
    
    # 异常情况 - 反向开仓
    with pytest.raises(AssertionError):
        pos.commit_open_new(price=50000.0, qty=-1.0)

def test_position_close_partial():
    """测试部分平仓"""
    pos = Position(symbol="BTC-USDT", leverage=2.0)
    pos.commit_open_new(price=50000.0, qty=2.0)
    pos.update_price_and_pnl(51000.0)
    
    # 部分平仓
    released_margin, realized_pnl = pos.commit_close_partial(price=51000.0, qty=-1.0)
    assert released_margin == 25000.0
    assert realized_pnl == 1000.0
    assert pos.size == 1.0
    
    # 全部平仓
    released_margin, realized_pnl = pos.commit_close_partial(price=51000.0, qty=-1.0)
    assert pos.is_empty()
    
    # 异常情况
    with pytest.raises(ValueError):
        pos.commit_close_partial(price=51000.0, qty=-1.0)  # 超过持仓量
    with pytest.raises(AssertionError):
        pos.commit_close_partial(price=51000.0, qty=1.0)   # 同向

def test_position_properties():
    """测试Position的属性方法"""
    pos = Position(symbol="BTC-USDT", leverage=2.0)
    pos.commit_open_new(price=50000.0, qty=1.0)
    
    # 测试方向
    assert pos.side == "long"
    pos.commit_close_all(50000.0)
    assert pos.side == "none"
    pos.commit_open_new(price=50000.0, qty=-1.0)
    assert pos.side == "short"
    
    # 测试杠杆率
    assert pos.leverage_ratio == 2.0
    
    # 测试保证金率
    pos.update_price_and_pnl(51000.0)
    expected_margin_level = pos.margin / pos.equity
    assert abs(pos.margin_level - expected_margin_level) < 1e-9

def test_order_initialization():
    """测试Order类的初始化"""
    # 正常初始化
    order = Order(symbol="BTC-USDT", leverage=2.0, price=50000.0, qty=1.0)
    assert order.symbol == "BTC-USDT"
    assert order.leverage == 2.0
    assert order.price == 50000.0
    assert order.qty == 1.0
    assert order.last_price is None
    assert order.fee == 0
    
    # 异常情况
    with pytest.raises(AssertionError):
        Order(symbol="", leverage=2.0, price=50000.0, qty=1.0)
    with pytest.raises(AssertionError):
        Order(symbol="BTC-USDT", leverage=0, price=50000.0, qty=1.0)
    with pytest.raises(AssertionError):
        Order(symbol="BTC-USDT", leverage=2.0, price=0, qty=1.0)

def test_position_complex_operations():
    """测试复杂的仓位操作组合"""
    pos = Position(symbol="BTC-USDT", leverage=2.0)
    
    # 开仓 -> 加仓 -> 部分平仓 -> 反向开仓
    pos.commit_open_new(price=50000.0, qty=1.0)
    pos.update_price_and_pnl(51000.0)
    pos.commit_open_new(price=51000.0, qty=1.0)
    pos.commit_close_partial(price=52000.0, qty=-1.5)
    
    assert pos.size == 0.5
    assert pos.side == "long"
    
    # 检查保证金和PnL计算的准确性
    expected_margin = 50500.0 * 0.5 / 2.0  # (平均成本 * 剩余数量) / 杠杆
    assert abs(pos.margin - expected_margin) < 1e-9 