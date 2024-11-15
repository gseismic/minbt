import pytest
import numpy as np
from minbt.broker.struct import Position

def test_position_initialization():
    """测试 Position 类的初始化"""
    # 正常初始化 - 现在支持可变杠杆
    pos = Position(symbol="BTC-USDT")
    assert pos.symbol == "BTC-USDT"
    assert pos.current_leverage() == 0
    assert pos.size == 0
    assert pos.cost_price == 0
    assert pos.margin == 0
    assert pos.last_price is None
    assert pos.unrealized_pnl == 0
    assert pos.equity == 0
    assert pos.is_empty()
    assert pos.side == "none"
    print(pos)


def test_position_open_new():
    """测试开新仓位"""
    pos = Position(symbol="BTC-USDT")
    
    leverage=2.0
    # 首次开多仓
    released_margin, realized_pnl = pos.commit_open_new(price=50000.0, qty=1.0, leverage=leverage)
    assert released_margin == -25000.0  # 占用保证金
    assert realized_pnl == 0
    assert pos.size == 1.0
    assert pos.cost_price == 50000.0
    assert pos.margin == 25000.0
    assert pos.side == "long"
    
    # 同向加仓
    released_margin, realized_pnl = pos.commit_open_new(price=51000.0, qty=1.0, leverage=leverage)
    assert released_margin == -25500.0
    assert realized_pnl == 0
    assert pos.size == 2.0
    assert abs(pos.cost_price - 50500.0) < 1e-9  # 考虑浮点数精度
    
    # 测试开空仓
    pos_short = Position(symbol="BTC-USDT")
    released_margin, realized_pnl = pos_short.commit_open_new(price=50000.0, qty=-1.0, leverage=leverage)
    assert pos_short.side == "short"
    
    # 异常情况 - 反向开仓
    with pytest.raises(AssertionError):
        pos.commit_open_new(price=50000.0, qty=-1.0, leverage=leverage)  # 多仓不能开空
    with pytest.raises(AssertionError):
        pos_short.commit_open_new(price=50000.0, qty=1.0, leverage=leverage)  # 空仓不能开多

def test_position_close_partial():
    """测试部分平仓"""
    pos = Position(symbol="BTC-USDT")
    leverage=2.0
    pos.commit_open_new(price=50000.0, qty=2.0, leverage=leverage)
    pos.update_price_and_pnl(51000.0)
    
    # 部分平仓
    released_margin, realized_pnl = pos.commit_close_partial(price=51000.0, qty=-1.0)
    assert released_margin == 25000.0
    assert realized_pnl == 1000.0
    assert pos.size == 1.0
    assert pos.side == "long"
    
    # 全部平仓
    released_margin, realized_pnl = pos.commit_close_partial(price=51000.0, qty=-1.0)
    assert pos.is_empty()
    assert pos.side == "none"
    
    # 异常情况
    with pytest.raises(AssertionError):
        pos.commit_close_partial(price=51000.0, qty=-1.0)  # 超过持仓量
    with pytest.raises(AssertionError):
        pos.commit_close_partial(price=51000.0, qty=1.0)   # 同向

def test_position_pnl_calculation():
    """测试盈亏计算"""
    pos = Position(symbol="BTC-USDT")
    leverage=2.0 
    released_margin, realized_pnl = pos.commit_open_new(price=50000.0, qty=1.0, leverage=leverage)
    assert released_margin == -25000.0
    assert realized_pnl == 0
    
    # 盈利情况
    pos.update_price_and_pnl(51000.0)
    assert pos.unrealized_pnl == 1000.0
    assert pos.equity == 26000.0  # margin + unrealized_pnl
    
    # 亏损情况
    pos.update_price_and_pnl(49000.0)
    assert pos.unrealized_pnl == -1000.0
    assert pos.equity == 24000.0

def test_position_leverage_and_margin():
    """测试杠杆和保证金相关计算"""
    pos = Position(symbol="BTC-USDT")
    leverage=2.0
    released_margin, realized_pnl = pos.commit_open_new(price=50000.0, qty=1.0, leverage=leverage)
    assert released_margin == -25000.0
    assert realized_pnl == 0
    
    # 测试杠杆率
    assert pos.current_leverage() == 2.0
    # 测试保证金率
    pos.update_price_and_pnl(51000.0)
    expected_margin_level = pos.equity/pos.margin
    assert abs(pos.margin_level - expected_margin_level) < 1e-9

def test_position_close_all():
    """测试全部平仓"""
    pos = Position(symbol="BTC-USDT")
    leverage=2.0
    released_margin, realized_pnl = pos.commit_open_new(price=50000.0, qty=2.0, leverage=leverage)
    assert released_margin == -50000.0
    assert realized_pnl == 0
    pos.update_price_and_pnl(51000.0)
    
    # 使用当前价格平仓
    released_margin, realized_pnl = pos.commit_close_all()
    assert pos.is_empty()
    assert released_margin == 50000.0
    assert realized_pnl == 2000.0
    
    # 使用指定价格平仓
    released_margin, realized_pnl = pos.commit_open_new(price=50000.0, qty=2.0, leverage=leverage)
    pos.update_price_and_pnl(52000.0)  # 先更新价格
    released_margin, realized_pnl = pos.commit_close_all(52000.0)
    assert pos.is_empty()
    assert released_margin == 50000.0
    assert realized_pnl == 4000.0  # (52000 - 50000) * 2


if __name__ == "__main__":
    # pytest.main([__file__])
    test_position_initialization()
    test_position_open_new()
    test_position_close_partial()
    test_position_pnl_calculation()
    test_position_leverage_and_margin()
    test_position_close_all()
