import pytest
from minbt.broker import Broker #, PositionStats
from minbt.logger import I18nLogger

def test_broker_init():
    """测试Broker初始化"""
    broker = Broker(initial_cash=10000, fee_rate=0.001)
    assert broker.initial_cash == 10000
    assert broker.total_cash == 10000
    assert broker.free_cash == 10000
    assert broker.locked_cash == 0
    assert broker.fee_rate == 0.001
    assert broker.leverage == 1.0
    assert broker.margin_mode == 'cross'
    assert broker.positions == {}

def test_cross_margin_trading():
    """测试全仓交易"""
    broker = Broker(
        initial_cash=10000,
        fee_rate=0.001,
        leverage=5,
        margin_mode='cross'
    )
    
    # 测试开仓
    pos = broker.buy('BTC', price=50000, qty=0.1)
    assert isinstance(pos, PositionStats)
    assert pos.position_size == 0.1
    assert pos.fee > 0
    
    # 测试更新价格
    pos = broker.update_price('BTC', 51000)
    assert pos.gross_profit > 0
    
    # 测试平仓
    pos = broker.sell('BTC', price=51000, qty=0.1)
    assert pos.position_size == 0

def test_isolated_margin_trading():
    """测试逐仓交易"""
    broker = Broker(
        initial_cash=10000,
        fee_rate=0.001,
        leverage=5,
        margin_mode='isolated'
    )
    
    # 测试分配保证金
    broker.allocate_margin('BTC', 2000)
    assert broker.allocated_margins['BTC'] == 2000
    
    # 测试开仓
    pos = broker.buy('BTC', price=50000, qty=0.1)
    assert pos.allocated_margin == 2000
    
    # 测试保证金率
    pos = broker.update_price('BTC', 48000)
    assert pos.margin_level < 1

def test_stop_orders():
    """测试止盈止损订单"""
    broker = Broker(initial_cash=10000, fee_rate=0.001)
    
    # 开仓
    broker.buy('BTC', price=50000, qty=0.1)
    
    # 添加止盈止损
    tp_id = broker.add_take_profit('BTC', price=51000)
    sl_id = broker.add_stop_loss('BTC', price=49000)
    
    assert tp_id and sl_id
    pos = broker.get_position('BTC')
    assert len(pos.stop_orders) == 2
    
    # 测试触发止盈
    pos = broker.update_price('BTC', 51500)
    assert pos.position_size == 0

def test_leverage_liquidation():
    """测试杠杆和爆仓"""
    broker = Broker(
        initial_cash=10000,
        fee_rate=0.001,
        leverage=10,
        margin_mode='isolated'
    )
    
    broker.allocate_margin('BTC', 1000)
    pos = broker.buy('BTC', price=50000, qty=0.1)
    
    # 价格大幅下跌应该触发爆仓
    pos = broker.update_price('BTC', 45000)
    assert pos.position_size == 0

def test_invalid_operations():
    """测试无效操作"""
    broker = Broker(initial_cash=10000, fee_rate=0.001)
    
    with pytest.raises(AssertionError):
        Broker(initial_cash=-1000, fee_rate=0.001)
    
    with pytest.raises(AssertionError):
        Broker(initial_cash=1000, fee_rate=1.5)
        
    # 测试超出可用保证金
    with pytest.raises(Exception):
        broker.buy('BTC', price=50000, qty=10)

if __name__ == "__main__":
    if 1:
        test_broker_init()
    if 0:
        test_cross_margin_trading()
    if 0:
        test_isolated_margin_trading()
    if 0:
        test_stop_orders()
    if 0:
        test_leverage_liquidation()
    if 0:
        test_invalid_operations()
