from minbt.broker.portfolio import Portfolio
import pytest

def test_portfolio_initialization():
    portfolio = Portfolio(
        initial_cash=100000,
        fee_rate=0.001,
        leverage=1.0,
        margin_mode='cross',
        warning_margin_level=0.2,
        min_margin_level=0.1
    )
    assert portfolio.total_cash == 100000
    assert portfolio.free_cash == 100000
    assert portfolio.locked_cash == 0
    assert len(portfolio.positions) == 0
    assert portfolio.get_portfolio_equity() == 100000

def test_portfolio_submit_order():
    portfolio = Portfolio(initial_cash=100000, fee_rate=0.001)
    
    # 测试开仓
    success = portfolio.submit_order("AAPL", qty=10, price=150.0)
    assert success
    return
    
    position = portfolio.get_position("AAPL")
    assert position.size == 10
    
    # 验证手续费和现金变化
    trade_value = 10 * 150.0
    fee = trade_value * 0.001
    expected_free_cash = 100000 - trade_value - fee
    assert pytest.approx(portfolio.free_cash) == expected_free_cash

def test_portfolio_margin_and_leverage():
    portfolio = Portfolio(
        initial_cash=100000,
        fee_rate=0.001,
        leverage=2.0,  # 2倍杠杆
        margin_mode='isolated'
    )
    
    # 使用杠杆开仓
    success = portfolio.submit_order("AAPL", qty=20, price=150.0, leverage=2.0)
    assert success
    
    position = portfolio.get_position("AAPL")
    assert position.size == 20
    assert position.current_leverage() == 2.0
    
    # 验证保证金
    position_value = 20 * 150.0
    expected_margin = position_value / 2.0  # 2倍杠杆意味着保证金是仓位价值的一半
    assert pytest.approx(position.margin) == expected_margin

def test_portfolio_close_position():
    portfolio = Portfolio(initial_cash=100000, fee_rate=0.001)
    
    # 开仓
    open_price = 150.0
    open_qty = 10
    open_value = open_qty * open_price
    open_fee = open_value * 0.001
    
    # print(f'open_value: {open_value}, open_fee: {open_fee}, {100000 - open_value=}')
    portfolio.submit_order("AAPL", qty=open_qty, price=open_price)
    assert pytest.approx(portfolio.free_cash) == 100000 - open_value - open_fee
    
    # 平仓
    close_price = 160.0
    close_qty = -10
    close_value = abs(close_qty) * close_price
    close_fee = close_value * 0.001
    
    portfolio.submit_order("AAPL", qty=close_qty, price=close_price)
    
    # 验证仓位已关闭
    position = portfolio.get_position("AAPL")
    assert position.size == 0
    
    # 验证现金变化
    # 1. 开仓：-开仓金额 - 开仓手续费
    # 2. 平仓：+平仓金额 - 平仓手续费
    expected_cash = (
        100000                  # 初始现金
        - open_value           # 开仓金额
        - open_fee            # 开仓手续费
        + close_value         # 平仓金额
        - close_fee          # 平仓手续费
    )
    
    print(f"""
    初始现金: {100000}
    开仓金额: {open_value}
    开仓手续费: {open_fee}
    平仓金额: {close_value}
    平仓手续费: {close_fee}
    期望现金: {expected_cash}
    实际现金: {portfolio.free_cash}
    """)
    
    assert pytest.approx(portfolio.free_cash) == expected_cash

def test_margin_liquidation():
    portfolio = Portfolio(
        initial_cash=100000,
        fee_rate=0.001,
        leverage=5.0,
        margin_mode='isolated',
        warning_margin_level=0.2,
        min_margin_level=0.1
    )
    
    # 开仓
    portfolio.submit_order("AAPL", qty=100, price=150.0, leverage=5.0)
    
    # 价格下跌触发强平
    bankrupt, reach_liquidation, margin_level = portfolio.on_new_price("AAPL", price=120.0)
    assert reach_liquidation
    
    # 验证仓位已被强平
    position = portfolio.get_position("AAPL")
    assert position.size == 0

def test_portfolio_value_calculation():
    portfolio = Portfolio(initial_cash=100000, fee_rate=0.001)
    
    # 开仓多个品种
    portfolio.submit_order("AAPL", qty=10, price=150.0)
    portfolio.submit_order("GOOGL", qty=5, price=2000.0)
    
    # 更新价格
    portfolio.on_new_price("AAPL", 160.0)
    portfolio.on_new_price("GOOGL", 2100.0)
    
    # 验证组合市值
    positions_value = portfolio.get_all_positions_total_equity()
    expected_positions_value = (10 * 160.0) + (5 * 2100.0)
    assert pytest.approx(positions_value) == expected_positions_value
    
    portfolio_value = portfolio.get_portfolio_equity()
    assert pytest.approx(portfolio_value) == positions_value + portfolio.total_cash

if __name__ == "__main__":
    # pytest.main([__file__])
    test_portfolio_initialization()
    test_portfolio_submit_order()
    test_portfolio_margin_and_leverage()
    test_portfolio_close_position()
    test_margin_liquidation()
    test_portfolio_value_calculation()
