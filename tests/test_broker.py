import pytest
from pytest import approx
from minbt.broker.broker import Broker
# from minbt.broker.struct import Order, OrderStatus, OrderType, OrderSide

def test_order_submission():
    """测试订单提交功能"""
    broker = Broker(initial_cash=10000, fee_rate=0.001)
    
    # 测试市价单提交
    order = broker.submit_market_order(
        symbol="BTCUSDT",
        qty=1.0,
        price=5000.0
    )
    
    broker.on_new_price("BTCUSDT", 5000.0)
    assert broker.get_market_price("BTCUSDT") == 5000.0
    assert broker.get_position("BTCUSDT").size == 1.0
    assert not broker.portfolios['default'].bankrupt

    assert approx(broker.portfolios['default'].cash) == 10000 - 5000 * 1.0 * (1 + 0.001)
    print(f'total_equity: {broker.get_total_equity()}')

    broker.on_new_price("BTCUSDT", 6000.0)
    print(f'total_equity: {broker.get_total_equity()}')
    broker.on_new_price("BTCUSDT", 5000.0)
    print(f'total_equity: {broker.get_total_equity()}')
    print(f'total_initial_cash: {broker.initial_cash}')
    
    # assert order.status == OrderStatus.FILLED
    # assert order.type == OrderType.MARKET
    # assert order.filled_qty == 1.0
    
    # 测试限价单提交
    # order = broker.submit_limit_order(
    #     symbol="BTCUSDT",
    #     qty=0.5,
    #     side=OrderSide.SELL,
    #     price=55000.0
    # )
    # assert order.status == OrderStatus.PENDING
    # assert order.type == OrderType.LIMIT
    # assert order.filled_qty == 0

# def test_position_management():
#     """测试仓位管理"""
#     broker = Broker(initial_cash=10000, fee_rate=0.001)
    
#     # 开仓
#     broker.submit_market_order("BTCUSDT", 1.0, OrderSide.BUY, 50000.0)
#     position = broker.get_position("BTCUSDT")
#     assert position.size == 1.0
#     assert position.avg_price == 50000.0
    
#     # 加仓
#     broker.submit_market_order("BTCUSDT", 0.5, OrderSide.BUY, 48000.0)
#     assert position.size == 1.5
#     assert pytest.approx(position.avg_price) == 49333.33  # (50000*1 + 48000*0.5)/1.5
    
#     # 减仓
#     broker.submit_market_order("BTCUSDT", 1.0, OrderSide.SELL, 52000.0)
#     assert position.size == 0.5

# def test_cash_management():
#     """测试资金管理"""
#     initial_cash = 10000
#     broker = Broker(initial_cash=initial_cash, fee_rate=0.001)
    
#     # 买入消耗资金
#     price = 100.0
#     qty = 10
#     fee = price * qty * 0.001
#     broker.submit_market_order("AAPL", qty, OrderSide.BUY, price)
#     expected_cash = initial_cash - (price * qty + fee)
#     assert pytest.approx(broker.cash) == expected_cash
    
#     # 卖出增加资金
#     sell_price = 110.0
#     sell_fee = sell_price * qty * 0.001
#     broker.submit_market_order("AAPL", qty, OrderSide.SELL, sell_price)
#     profit = (sell_price - price) * qty - fee - sell_fee
#     assert pytest.approx(broker.cash) == initial_cash + profit

# def test_order_cancellation():
#     """测试订单取消"""
#     broker = Broker(initial_cash=10000, fee_rate=0.001)
    
#     # 提交限价单
#     order = broker.submit_limit_order(
#         symbol="BTCUSDT",
#         qty=1.0,
#         side=OrderSide.BUY,
#         price=45000.0
#     )
#     order_id = order.order_id
    
#     # 取消订单
#     success = broker.cancel_order(order_id)
#     assert success
#     assert broker.get_order(order_id).status == OrderStatus.CANCELLED

# def test_margin_trading():
#     """测试保证金交易"""
#     broker = Broker(initial_cash=10000, fee_rate=0.001, leverage=3.0)
    
#     # 测试杠杆开仓
#     order = broker.submit_market_order(
#         symbol="BTCUSDT",
#         qty=1.0,
#         side=OrderSide.BUY,
#         price=30000.0,
#         leverage=3.0
#     )
#     position = broker.get_position("BTCUSDT")
#     assert position.leverage == 3.0
#     assert position.margin == 10000.0  # 30000/3
    
#     # 测试保证金率计算
#     broker.update_market_price("BTCUSDT", 33000.0)  # 价格上涨10%
#     assert pytest.approx(position.margin_level) == 1.1  # (10000 + 3000) / 10000

# def test_error_handling():
#     """测试错误处理"""
#     broker = Broker(initial_cash=10000, fee_rate=0.001)
    
#     # 测试资金不足
#     order = broker.submit_market_order(
#         symbol="BTCUSDT",
#         qty=1.0,
#         side=OrderSide.BUY,
#         price=20000.0
#     )
#     assert order.status == OrderStatus.REJECTED
    
#     # 测试取消不存在的订单
#     success = broker.cancel_order("non_existent_order_id")
#     assert not success
    
#     # 测试无效的订单数量
#     order = broker.submit_market_order(
#         symbol="BTCUSDT",
#         qty=0,
#         side=OrderSide.BUY,
#         price=10000.0
#     )
#     assert order.status == OrderStatus.REJECTED

if __name__ == "__main__":
    # pytest.main([__file__])
    test_order_submission()
