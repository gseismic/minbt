import pytest
import os
import subprocess
import sys
from pathlib import Path
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

def test_add_sub_portfolio_rejects_duplicate_id():
    """测试不能重复添加同名子组合"""
    broker = Broker(initial_cash=1000, fee_rate=0, portfolio_cash=600)
    remaining_cash = broker.remaining_free_cash
    original_portfolio = broker.portfolios['default']

    with pytest.raises(ValueError):
        broker.add_sub_portfolio('default', 100)

    assert broker.remaining_free_cash == remaining_cash
    assert broker.portfolios['default'] is original_portfolio

def test_add_sub_portfolio_rejects_insufficient_cash():
    """测试子组合资金不能超过未分配现金"""
    broker = Broker(initial_cash=1000, fee_rate=0, portfolio_cash=600)

    with pytest.raises(ValueError):
        broker.add_sub_portfolio('alt', 500)

    assert broker.remaining_free_cash == 400
    assert 'alt' not in broker.portfolios

def test_submit_market_order_requires_existing_portfolio_before_price_update():
    """测试无效组合不会污染 broker 或组合行情状态"""
    broker = Broker(initial_cash=1000, fee_rate=0)

    with pytest.raises(ValueError):
        broker.submit_market_order("AAPL", qty=1, price=100, portfolio_id="missing")

    assert broker.last_prices == {}
    assert broker.portfolios['default'].positions == {}

def test_submit_market_order_requires_known_price():
    """测试未提供价格且无最新价时给出明确错误"""
    broker = Broker(initial_cash=1000, fee_rate=0)

    with pytest.raises(ValueError):
        broker.submit_market_order("AAPL", qty=1)

    assert broker.portfolios['default'].positions == {}

def test_position_size_query_does_not_create_empty_position():
    """测试只读持仓数量查询不会创建空仓位"""
    broker = Broker(initial_cash=1000, fee_rate=0)

    assert broker.get_position_size('UNKNOWN') == 0
    assert broker.get_position('UNKNOWN', create_if_missing=False) is None
    assert broker.portfolios['default'].positions == {}

def test_total_equity_includes_all_portfolios_and_unallocated_cash():
    """测试 broker 总权益包含所有子组合和未分配现金"""
    broker = Broker(initial_cash=1000, fee_rate=0, portfolio_cash=600)
    broker.add_sub_portfolio('alt', 300)

    assert broker.get_all_portfolio_equity() == 900
    assert broker.remaining_free_cash == 100
    assert broker.get_total_equity() == 1000
    assert broker.get_equity() == 600

def test_broker_rejects_invalid_margin_config():
    """测试保证金阈值规则在 Broker 和 Portfolio 一致"""
    with pytest.raises(ValueError):
        Broker(initial_cash=1000, fee_rate=0, warning_margin_level=0.1, min_margin_level=0.1)

    with pytest.raises(ValueError):
        Broker(initial_cash=1000, fee_rate=0, warning_margin_level=1.0, min_margin_level=0.1)

def test_broker_validation_survives_optimized_python():
    """测试 python -O 下输入校验不会被跳过"""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env['PYTHONPATH'] = str(repo_root) + os.pathsep + env.get('PYTHONPATH', '')
    code = """
from minbt import Broker
try:
    Broker(initial_cash=1000, fee_rate=2, portfolio_cash=2000, leverage=0)
except ValueError:
    raise SystemExit(0)
raise SystemExit(1)
"""

    result = subprocess.run(
        [sys.executable, '-O', '-c', code],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr

def test_close_portfolio_keeps_portfolio_when_close_fails():
    """测试关闭组合失败时不会先移除组合导致状态丢失"""
    broker = Broker(initial_cash=1000, fee_rate=0)
    portfolio = broker.portfolios['default']

    def fail_close_all_positions(last_prices):
        raise RuntimeError('close failed')

    portfolio.close_all_positions = fail_close_all_positions

    with pytest.raises(RuntimeError, match='close failed'):
        broker.close_portfolio('default')

    assert broker.portfolios['default'] is portfolio

if __name__ == "__main__":
    # pytest.main([__file__])
    test_order_submission()
