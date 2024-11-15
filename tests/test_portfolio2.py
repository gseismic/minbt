from minbt.broker.portfolio import Portfolio
import pytest
import numpy as np

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
    assert position.leverage == 5.0
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
        initial_equity = total_margin = 5000
        
    3. 价格下跌40%: (需要更大的跌幅才能触发警告)
        AAPL: unrealized_pnl = (60 - 100) * 100 = -4000
        GOOGL: unrealized_pnl = (600 - 1000) * 5 = -2000
        total_equity = 5000 - 4000 - 2000 = -1000
        margin_level = -1000 / 5000 = -0.2
        
    4. 继续下跌50%:
        AAPL: unrealized_pnl = (50 - 100) * 100 = -5000
        GOOGL: unrealized_pnl = (500 - 1000) * 5 = -2500
        total_equity = 5000 - 5000 - 2500 = -2500
        margin_level = -2500 / 5000 = -0.5
    """
    portfolio = Portfolio(
        initial_cash=10000,
        fee_rate=0.001,
        leverage=3.0,
        margin_mode='cross',
        warning_margin_level=0.2,
        min_margin_level=0.1
    )
    
    # 开多个仓位
    portfolio.submit_order("AAPL", qty=100, price=100.0)  # 价值10,000，需要保证金3,333
    portfolio.submit_order("GOOGL", qty=5, price=1000.0)  # 价值5,000，需要保证金1,667
    
    # 验证初始状态
    total_margin = portfolio.get_all_positions_total_margin()  # 5000
    total_equity = portfolio.get_all_positions_total_equity()  # 5000
    # print(f'{portfolio.positions=}')
    assert total_equity == total_margin
    assert pytest.approx(total_equity) == 5000
    assert pytest.approx(portfolio.get_portfolio_margin_level()) == total_equity / total_margin  # 1.0
    
    # 价格下跌40%，应该触发警告和强平
    portfolio.on_new_price("AAPL", 60.0)  # -4000
    portfolio.on_new_price("GOOGL", 600.0)  # -2000
    assert portfolio.bankrupt
    margin_level = portfolio.get_portfolio_margin_level()  # -0.2
    # print(f'---{margin_level=}')
    assert margin_level <= portfolio.warning_margin_level  # -0.2 < 0.2
    assert len(portfolio.positions) == 0  # 权益为负，应该触发强平

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
    assert pytest.approx(position.leverage_ratio) == 2.5  # 加权平均杠杆

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
    assert "AAPL" not in portfolio.positions
    
    # 开仓后剩余保证金不足以开新仓
    portfolio.submit_order("AAPL", qty=400, price=100.0)  # 使用8000保证金
    success = portfolio.submit_order("GOOGL", qty=100, price=100.0)  # 尝试使用2000保证金
    assert not success
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
    success = portfolio.submit_order("AAPL", qty=0.0001, price=100.0)
    assert success
    
    # 测试开仓后立即平仓
    portfolio.submit_order("AAPL", qty=100, price=100.0)
    portfolio.submit_order("AAPL", qty=-100, price=100.0)
    assert portfolio.get_position("AAPL").size == 0
    
    # 测试未初始化价格的仓位计算
    portfolio.submit_order("GOOGL", qty=10, price=1000.0)
    assert portfolio.get_position("GOOGL").last_price == 1000.0

if __name__ == "__main__":
    # pytest.main([__file__])
    # test_isolated_margin_liquidation()
    # test_cross_margin_liquidation()
    test_leverage_change()
    # test_insufficient_margin()
    # test_position_transfer()
    # test_edge_cases()
