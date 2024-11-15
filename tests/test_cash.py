import pytest
from minbt.broker.struct import Cash

# 忽略 Jupyter 路径迁移警告
# pytestmark = pytest.mark.filterwarnings(
#     "ignore:Jupyter is migrating its paths:DeprecationWarning"
# )

def test_cash_initialization():
    """测试 Cash 类的初始化"""
    # 正常初始化
    cash = Cash(total_cash=1000.0, free_cash=800.0)
    assert cash.total_cash == 1000.0
    assert cash.free_cash == 800.0
    assert cash.locked_cash == 200.0

    # 边界情况测试
    cash = Cash(total_cash=1000.0, free_cash=1000.0)
    assert cash.locked_cash == 0.0

    # 异常情况测试
    with pytest.raises(AssertionError):
        Cash(total_cash=-1000.0, free_cash=800.0)  # 负总现金
    
    with pytest.raises(AssertionError):
        Cash(total_cash=1000.0, free_cash=-800.0)  # 负可用现金
    
    with pytest.raises(AssertionError):
        Cash(total_cash=800.0, free_cash=1000.0)  # 可用现金大于总现金

def test_cash_add():
    """测试添加现金功能"""
    cash = Cash(total_cash=1000.0, free_cash=800.0)
    
    # 正常添加
    cash.add_cash(amount=200.0)
    assert cash.total_cash == 1200.0
    assert cash.free_cash == 1000.0
    assert cash.locked_cash == 200.0

    # 添加0
    cash.add_cash(amount=0.0)
    assert cash.total_cash == 1200.0
    assert cash.free_cash == 1000.0

    # 异常情况
    with pytest.raises(AssertionError):
        cash.add_cash(amount=-100.0)  # 不能添加负现金

def test_cash_spend():
    """测试花费现金功能"""
    cash = Cash(total_cash=1000.0, free_cash=800.0)
    
    # 正常花费
    cash.spend_cash(amount=300.0)
    assert cash.total_cash == 700.0
    assert cash.free_cash == 500.0
    assert cash.locked_cash == 200.0  # 锁定金额不变

    # 花费0
    cash.spend_cash(amount=0.0)
    assert cash.total_cash == 700.0
    assert cash.free_cash == 500.0
    assert cash.locked_cash == 200.0

    # 异常情况
    with pytest.raises(AssertionError):
        cash.spend_cash(amount=-100.0)  # 不能花费负现金
    
    with pytest.raises(AssertionError):
        cash.spend_cash(amount=600.0)  # 不能花费超过可用现金的金额

def test_cash_lock_unlock():
    """测试锁定和解锁现金功能"""
    cash = Cash(total_cash=1000.0, free_cash=800.0)
    
    # 测试锁定
    cash.lock_cash(amount=300.0)
    assert cash.free_cash == 500.0
    assert cash.locked_cash == 500.0
    assert cash.total_cash == 1000.0

    # 测试解锁
    cash.unlock_cash(amount=200.0)
    assert cash.free_cash == 700.0
    assert cash.locked_cash == 300.0
    assert cash.total_cash == 1000.0

    # 异常情况 - 锁定
    with pytest.raises(AssertionError):
        cash.lock_cash(amount=-100.0)  # 不能锁定负现金
    
    with pytest.raises(AssertionError):
        cash.lock_cash(amount=800.0)  # 不能锁定超过可用现金的金额

    # 异常情况 - 解锁
    with pytest.raises(AssertionError):
        cash.unlock_cash(amount=-100.0)  # 不能解锁负现金
    
    with pytest.raises(AssertionError):
        cash.unlock_cash(amount=400.0)  # 不能解锁超过已锁定现金的金额

def test_cash_representation():
    """测试现金对象的字符串表示"""
    cash = Cash(total_cash=1000.0, free_cash=800.0)
    expected_repr = "Cash(total_cash=1000.0, free_cash=800.0, locked_cash=200.0)"
    assert str(cash) == expected_repr
    assert repr(cash) == expected_repr

def test_cash_complex_operations():
    """测试复杂的现金操作组合"""
    cash = Cash(total_cash=1000.0, free_cash=1000.0)
    
    # 一系列操作
    cash.lock_cash(amount=300.0)    # 锁定300: free=700, locked=300, total=1000
    cash.add_cash(amount=500.0)     # 添加500: free=1200, locked=300, total=1500
    cash.spend_cash(amount=200.0)   # 花费200: free=1000, locked=300, total=1300
    cash.unlock_cash(amount=100.0)  # 解锁100: free=1100, locked=200, total=1300
    
    # 最终状态验证
    assert cash.total_cash == 1300.0  # 1000 + 500 - 200
    assert cash.free_cash == 1100.0   # 1000 - 300 + 500 - 200 + 100
    assert cash.locked_cash == 200.0  # 300 - 100

def test_cash_edge_cases():
    """测试边界情况"""
    # 最小值测试
    cash = Cash(total_cash=0.0, free_cash=0.0)
    assert cash.total_cash == 0.0
    assert cash.free_cash == 0.0
    assert cash.locked_cash == 0.0

    # 精度测试
    cash = Cash(total_cash=1000.123456789, free_cash=1000.123456789)
    assert abs(cash.total_cash - 1000.123456789) < 1e-9
    assert abs(cash.free_cash - 1000.123456789) < 1e-9 