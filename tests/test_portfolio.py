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
    
    # 开仓
    success = portfolio.submit_order("AAPL", qty=10, price=150.0)
    assert success
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

def test_on_new_price_does_not_create_empty_position():
    """测试行情更新不会为无持仓标的创建空仓位"""
    portfolio = Portfolio(initial_cash=100000, fee_rate=0.001)

    bankrupt, liquidated, margin_level = portfolio.on_new_price("AAPL", price=150.0)

    assert not bankrupt
    assert not liquidated
    assert margin_level == 1.0
    assert portfolio.positions == {}
    assert portfolio.last_prices["AAPL"] == 150.0

def test_portfolio_close_position_method():
    """测试 close_position 方法正确使用 -position.size 平仓"""
    portfolio = Portfolio(initial_cash=100000, fee_rate=0.001)

    # 开多仓
    portfolio.submit_order("AAPL", qty=10, price=150.0)
    position = portfolio.get_position("AAPL")
    assert position.size == 10

    # 使用 close_position 平仓
    portfolio.close_position("AAPL", last_price=160.0)
    position = portfolio.get_position("AAPL")
    assert position.size == 0

    # 开空仓再平仓
    portfolio2 = Portfolio(initial_cash=100000, fee_rate=0.001)
    portfolio2.submit_order("AAPL", qty=-10, price=150.0)
    assert portfolio2.get_position("AAPL").size == -10

    portfolio2.close_position("AAPL", last_price=140.0)
    assert portfolio2.get_position("AAPL").size == 0

def test_portfolio_close_empty_position():
    """测试对空头寸调用 close_position 不会出错"""
    portfolio = Portfolio(initial_cash=100000, fee_rate=0.001)
    result = portfolio.close_position("AAPL", last_price=150.0)
    assert result is False
    assert portfolio.get_position("AAPL").is_empty()

def test_isolated_margin_liquidation():
    """测试逐仓保证金强平
    计算过程:
    1. 开仓:
        position_value = qty * price = 400 * 100 = 40000
        required_margin = position_value / leverage = 40000 / 5 = 8000
        fee = qty * price * fee_rate = 400 * 100 * 0.001 = 40
        
    2. 价格下跌40%:
        new_price = 100 * 0.6 = 60
        position_value = qty * new_price = 400 * 60 = 24000
        unrealized_pnl = (new_price - price) * qty = (60 - 100) * 400 = -16000
        equity = margin + unrealized_pnl = 8000 - 16000 = -8000
        margin_level = equity / margin = -8000 / 8000 = -1.0
        
    3. 价格下跌50%:
        new_price = 100 * 0.5 = 50
        position_value = qty * new_price = 400 * 50 = 20000
        unrealized_pnl = (new_price - price) * qty = (50 - 100) * 400 = -20000
        equity = margin + unrealized_pnl = 8000 - 20000 = -12000
        margin_level = equity / margin = -12000 / 8000 = -1.5
    """
    portfolio = Portfolio(
        initial_cash=10000,
        fee_rate=0.001,
        leverage=5.0,
        margin_mode='isolated',
        warning_margin_level=0.2,
        min_margin_level=0.1
    )

    # 开仓 5倍杠杆
    price = 100.0
    qty = 400  # 持仓价值 40,000，需要保证金 8,000
    portfolio.submit_order("AAPL", qty=qty, price=price)
    position = portfolio.get_position("AAPL")
    
    # 验证初始状态
    assert position.size == qty
    assert position.current_leverage() == 5.0
    assert pytest.approx(position.margin) == qty * price / 5.0  # 8000
    assert pytest.approx(position.margin_level) == 1.0
    
    # 价格下跌40%，应该触发穿仓
    new_price = price * 0.6  # 60
    bankrupt, liquidated, margin_level = portfolio.on_new_price("AAPL", new_price)
    assert bankrupt  # 权益为负，触发穿仓
    assert liquidated  # 触发强平
    assert margin_level < 0  # margin_level = -1.0
    assert position.size == 0  # 仓位已被清空

def test_cross_margin_liquidation():
    """测试全仓保证金强平
    计算过程:
    1. 开仓AAPL:
        value = qty * price = 100 * 100 = 10000
        margin = value / leverage = 10000 / 3 ≈ 3333
        
    2. 开仓GOOGL:
        value = qty * price = 5 * 1000 = 5000
        margin = value / leverage = 5000 / 3 ≈ 1667
        total_margin = 3333 + 1667 = 5000
        free_cash = 5000
        account_equity = free_cash + total_margin = 10000
        margin_level = account_equity / total_margin = 2.0
        
    3. 价格下跌65%:
        AAPL: unrealized_pnl = (35 - 100) * 100 = -6500
        GOOGL: unrealized_pnl = (350 - 1000) * 5 = -3250
        account_equity = 10000 - 6500 - 3250 = 250
        margin_level = 250 / 5000 = 0.05，触发强平但未穿仓
    """
    portfolio = Portfolio(
        initial_cash=10000,
        fee_rate=0,
        leverage=3.0,
        margin_mode='cross',
        warning_margin_level=0.2,
        min_margin_level=0.1
    )
    
    # 开多个仓位
    portfolio.submit_order("AAPL", qty=100, price=100.0)  # 价值10,000，需要保证金3,333
    portfolio.submit_order("GOOGL", qty=5, price=1000.0)  # 价值5,000，需要保证金1,667
    
    # 验证初始状态
    total_margin = portfolio.get_all_positions_total_margin()
    assert pytest.approx(total_margin) == 5000
    assert pytest.approx(portfolio.get_all_positions_total_equity()) == 5000
    assert pytest.approx(portfolio.get_portfolio_equity()) == 10000
    assert pytest.approx(portfolio.get_portfolio_margin_level()) == 2.0

    # 价格下跌65%，账户权益仍为正，应该强平但不标记穿仓
    portfolio.on_new_price("AAPL", 35.0)
    bankrupt, liquidated, margin_level = portfolio.on_new_price("GOOGL", 350.0)
    assert not bankrupt
    assert liquidated
    assert pytest.approx(margin_level) == 0.05
    assert not portfolio.bankrupt
    assert pytest.approx(portfolio.total_cash) == 250
    assert pytest.approx(portfolio.get_portfolio_equity()) == 250
    assert all(position.size == 0 for position in portfolio.positions.values())

def test_cross_margin_uses_free_cash_before_liquidation():
    """测试全仓模式下可用现金会作为风险缓冲，避免过早强平"""
    portfolio = Portfolio(
        initial_cash=10000,
        fee_rate=0,
        leverage=5.0,
        margin_mode='cross',
        warning_margin_level=0.2,
        min_margin_level=0.1
    )

    portfolio.submit_order("AAPL", qty=400, price=100.0)

    bankrupt, liquidated, margin_level = portfolio.on_new_price("AAPL", 80.0)

    assert not bankrupt
    assert not liquidated
    assert pytest.approx(margin_level) == 0.25
    assert portfolio.get_position("AAPL").size == 400
    assert pytest.approx(portfolio.get_portfolio_equity()) == 2000

def test_cross_margin_bankruptcy_wipes_account_cash():
    """测试全仓穿仓后不会因清空持仓而把剩余现金错误算作权益"""
    portfolio = Portfolio(
        initial_cash=10000,
        fee_rate=0,
        leverage=5.0,
        margin_mode='cross',
        warning_margin_level=0.2,
        min_margin_level=0.1
    )

    portfolio.submit_order("AAPL", qty=400, price=100.0)
    bankrupt, liquidated, margin_level = portfolio.on_new_price("AAPL", 74.0)

    assert bankrupt
    assert liquidated
    assert margin_level < 0
    assert portfolio.bankrupt
    assert portfolio.positions == {}
    assert portfolio.total_cash == 0
    assert portfolio.get_portfolio_equity() == 0

def test_leverage_change():
    """测试杠杆变更
    计算过程:
    1. 第一次开仓:
        value1 = qty1 * price = 100 * 100 = 10000
        margin1 = value1 / leverage1 = 10000 / 2 = 5000
        
    2. 第二次开仓:
        value2 = qty2 * price = 50 * 100 = 5000
        margin2 = value2 / leverage2 = 5000 / 5 = 1000
        
    3. 最终状态:
        total_value = value1 + value2 = 15000
        total_margin = margin1 + margin2 = 6000
        avg_leverage = total_value / total_margin = 15000 / 6000 = 2.5
    """
    portfolio = Portfolio(
        initial_cash=10000,
        fee_rate=0.001,
        leverage=2.0
    )
    
    # 用不同杠杆开仓
    portfolio.submit_order("AAPL", qty=100, price=100.0, leverage=2.0)  # 保证金5000
    position = portfolio.get_position("AAPL")
    assert pytest.approx(position.margin) == 5000
    print(f'{position.margin=}')
    
    # 用更高杠杆追加
    portfolio.submit_order("AAPL", qty=50, price=100.0, leverage=5.0)  # 额外保证金1000
    assert position.size == 150
    print(f'{position.margin=}')
    assert pytest.approx(position.margin) == 6000  # 总保证金
    assert pytest.approx(position.current_leverage()) == 2.5  # 加权平均杠杆

def test_insufficient_margin():
    """测试保证金不足
    计算过程:
    1. 第一次尝试开仓:
        value = qty * price = 1000 * 100 = 100000
        required_margin = value / leverage = 100000 / 5 = 20000
        fee = 100000 * 0.001 = 100
        total_required = 20000 + 100 > 10000 (初始资金)
        
    2. 第二次开仓:
        value = qty * price = 400 * 100 = 40000
        required_margin = value / leverage = 40000 / 5 = 8000
        fee = 40000 * 0.001 = 40
        total_required = 8000 + 40 < 10000
        remaining_cash = 10000 - 8040 ≈ 1960
        
    3. 第三次尝试开仓:
        value = qty * price = 100 * 100 = 10000
        required_margin = value / leverage = 10000 / 5 = 2000
        fee = 10000 * 0.001 = 10
        total_required = 2000 + 10 > 1960
    """
    portfolio = Portfolio(
        initial_cash=10000,
        fee_rate=0.001,
        leverage=5.0
    )
    
    # 尝试开超过可用保证金的仓位
    success = portfolio.submit_order("AAPL", qty=1000, price=100.0)  # 需要保证金20,000
    assert not success
    assert portfolio.get_position('AAPL', create_if_missing=False) is None
    assert "AAPL" not in portfolio.positions
    
    # 开仓后剩余保证金不足以开新仓
    portfolio.submit_order("AAPL", qty=400, price=100.0)  # 使用8000保证金
    success = portfolio.submit_order("GOOGL", qty=100, price=100.0)  # 尝试使用2000保证金
    assert not success
    print(portfolio.positions)
    assert portfolio.get_position('GOOGL', create_if_missing=False) is None
    assert "GOOGL" not in portfolio.positions

def test_position_transfer():
    """测试仓位反转"""
    portfolio = Portfolio(
        initial_cash=10000,
        fee_rate=0.001,
        leverage=2.0
    )
    
    # 开多仓
    portfolio.submit_order("AAPL", qty=100, price=100.0)
    position = portfolio.get_position("AAPL")
    assert position.size == 100
    
    # 一次性转为空仓
    portfolio.submit_order("AAPL", qty=-200, price=110.0)  # 平掉100多仓，开100空仓
    print(position.size)
    assert position.size == -100
    
    # 分步转为多仓
    portfolio.submit_order("AAPL", qty=100, price=105.0)  # 先平掉空仓
    portfolio.submit_order("AAPL", qty=100, price=105.0)  # 再开多仓
    assert position.size == 100

def test_edge_cases():
    """测试边界情况"""
    portfolio = Portfolio(
        initial_cash=10000,
        fee_rate=0.001,
        leverage=2.0
    )
    
    # 测试数量为0的订单
    success = portfolio.submit_order("AAPL", qty=0, price=100.0)
    assert not success
    
    # 测试极小数量的订单
    success = portfolio.submit_order("AAPL", qty=0.001, price=100.0)
    assert success
    
    # 测试开仓后立即平仓
    portfolio.submit_order("AAPL", qty=100, price=100.0)
    portfolio.submit_order("AAPL", qty=-100, price=100.0)
    print(portfolio.get_position("AAPL").size)
    assert pytest.approx(portfolio.get_position("AAPL").size) == 0.001
    
    # 测试未初始化价格的仓位计算
    portfolio.submit_order("GOOGL", qty=10, price=1000.0)
    assert portfolio.get_position("GOOGL").last_price == 1000.0


if __name__ == "__main__":
    # pytest.main([__file__])
    test_portfolio_initialization()
    test_portfolio_submit_order()
    test_portfolio_margin_and_leverage()
    test_portfolio_close_position()
    test_portfolio_value_calculation()
