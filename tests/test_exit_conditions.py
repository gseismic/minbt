"""退出条件测试：覆盖 exit.py 工厂函数、空头退出、trailing_stop_amount。

分三类：
1. exit.py 4 个公开工厂函数的单元测试（多头/空头/零仓位/参数校验）
2. 空头仓位退出条件集成测试（止损/止盈/追踪止损 pct）
3. trailing_stop_amount 集成测试（多头/空头）
"""

import pytest
from pytest import approx

from minbt import Broker
from minbt.broker.exit import ExitContext, stop_loss_pct, take_profit_pct, stop_loss_price, take_profit_price
from minbt.broker.struct import Position


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_ctx(price, position, broker=None, state=None):
    """构造一个最小 ExitContext，供工厂函数 condition 调用使用。"""
    return ExitContext(
        order_id="test-order",
        symbol="TEST",
        portfolio="main",
        dt="2026-01-01",
        price=price,
        position=position,
        broker=broker,
        data=None,
        state=state if state is not None else {},
    )


def _long_position(cost=100):
    return Position(symbol="TEST", size=1, _cost_price=cost)


def _short_position(cost=100):
    return Position(symbol="TEST", size=-1, _cost_price=cost)


def _empty_position(cost=100):
    return Position(symbol="TEST", size=0, _cost_price=cost)


# ===========================================================================
# 第一类：exit.py 4 个工厂函数单元测试
# ===========================================================================

# --- stop_loss_pct ----------------------------------------------------------

def test_stop_loss_pct_long_triggers_when_price_drops():
    rule = stop_loss_pct(0.1)
    pos = _long_position(cost=100)
    # price <= 100 * (1 - 0.1) = 90 → 触发
    assert rule.condition(_make_ctx(90, pos)) is True
    assert rule.condition(_make_ctx(89, pos)) is True
    # 未跌破
    assert rule.condition(_make_ctx(91, pos)) is False


def test_stop_loss_pct_short_triggers_when_price_rises():
    rule = stop_loss_pct(0.1)
    pos = _short_position(cost=100)
    # price >= 100 * (1 + 0.1) ≈ 110.00000001 → 触发（用 111 避免浮点边界）
    assert rule.condition(_make_ctx(111, pos)) is True
    assert rule.condition(_make_ctx(110.01, pos)) is True
    # 未涨破
    assert rule.condition(_make_ctx(109, pos)) is False


def test_stop_loss_pct_returns_false_for_zero_position():
    rule = stop_loss_pct(0.1)
    pos = _empty_position()
    assert rule.condition(_make_ctx(50, pos)) is False
    assert rule.condition(_make_ctx(200, pos)) is False


def test_stop_loss_pct_rejects_non_positive_pct():
    with pytest.raises(ValueError, match="pct must be positive"):
        stop_loss_pct(0)
    with pytest.raises(ValueError, match="pct must be positive"):
        stop_loss_pct(-0.1)


def test_stop_loss_pct_default_name():
    rule = stop_loss_pct(0.05)
    assert rule.name == "stop_loss_0.05"


def test_stop_loss_pct_custom_name():
    rule = stop_loss_pct(0.05, name="my_stop")
    assert rule.name == "my_stop"


# --- take_profit_pct --------------------------------------------------------

def test_take_profit_pct_long_triggers_when_price_rises():
    rule = take_profit_pct(0.1)
    pos = _long_position(cost=100)
    # price >= 100 * (1 + 0.1) ≈ 110.00000001 → 触发（用 111 避免浮点边界）
    assert rule.condition(_make_ctx(111, pos)) is True
    assert rule.condition(_make_ctx(110.01, pos)) is True
    assert rule.condition(_make_ctx(109, pos)) is False


def test_take_profit_pct_short_triggers_when_price_drops():
    rule = take_profit_pct(0.1)
    pos = _short_position(cost=100)
    # price <= 100 * (1 - 0.1) = 90 → 触发
    assert rule.condition(_make_ctx(90, pos)) is True
    assert rule.condition(_make_ctx(89, pos)) is True
    assert rule.condition(_make_ctx(91, pos)) is False


def test_take_profit_pct_returns_false_for_zero_position():
    rule = take_profit_pct(0.1)
    pos = _empty_position()
    assert rule.condition(_make_ctx(50, pos)) is False
    assert rule.condition(_make_ctx(200, pos)) is False


def test_take_profit_pct_rejects_non_positive_pct():
    with pytest.raises(ValueError, match="pct must be positive"):
        take_profit_pct(0)
    with pytest.raises(ValueError, match="pct must be positive"):
        take_profit_pct(-0.1)


def test_take_profit_pct_default_name():
    rule = take_profit_pct(0.05)
    assert rule.name == "take_profit_0.05"


# --- stop_loss_price --------------------------------------------------------

def test_stop_loss_price_long_triggers_when_price_at_or_below():
    rule = stop_loss_price(95)
    pos = _long_position(cost=100)
    assert rule.condition(_make_ctx(95, pos)) is True
    assert rule.condition(_make_ctx(94, pos)) is True
    assert rule.condition(_make_ctx(96, pos)) is False


def test_stop_loss_price_short_triggers_when_price_at_or_above():
    rule = stop_loss_price(110)
    pos = _short_position(cost=100)
    assert rule.condition(_make_ctx(110, pos)) is True
    assert rule.condition(_make_ctx(111, pos)) is True
    assert rule.condition(_make_ctx(109, pos)) is False


def test_stop_loss_price_returns_false_for_zero_position():
    rule = stop_loss_price(95)
    pos = _empty_position()
    assert rule.condition(_make_ctx(50, pos)) is False
    assert rule.condition(_make_ctx(200, pos)) is False


def test_stop_loss_price_rejects_non_positive_price():
    with pytest.raises(ValueError, match="price must be positive"):
        stop_loss_price(0)
    with pytest.raises(ValueError, match="price must be positive"):
        stop_loss_price(-10)


def test_stop_loss_price_default_name():
    rule = stop_loss_price(95)
    assert rule.name == "stop_loss_price_95"


# --- take_profit_price ------------------------------------------------------

def test_take_profit_price_long_triggers_when_price_at_or_above():
    rule = take_profit_price(110)
    pos = _long_position(cost=100)
    assert rule.condition(_make_ctx(110, pos)) is True
    assert rule.condition(_make_ctx(111, pos)) is True
    assert rule.condition(_make_ctx(109, pos)) is False


def test_take_profit_price_short_triggers_when_price_at_or_below():
    rule = take_profit_price(90)
    pos = _short_position(cost=100)
    assert rule.condition(_make_ctx(90, pos)) is True
    assert rule.condition(_make_ctx(89, pos)) is True
    assert rule.condition(_make_ctx(91, pos)) is False


def test_take_profit_price_returns_false_for_zero_position():
    rule = take_profit_price(110)
    pos = _empty_position()
    assert rule.condition(_make_ctx(50, pos)) is False
    assert rule.condition(_make_ctx(200, pos)) is False


def test_take_profit_price_rejects_non_positive_price():
    with pytest.raises(ValueError, match="price must be positive"):
        take_profit_price(0)
    with pytest.raises(ValueError, match="price must be positive"):
        take_profit_price(-10)


def test_take_profit_price_default_name():
    rule = take_profit_price(110)
    assert rule.name == "take_profit_price_110"


# ===========================================================================
# 第二类：空头退出条件集成测试
# ===========================================================================

def test_short_stop_loss_price_triggers_close():
    """空头止损：开空 → 价格涨到止损价 → 触发平仓。"""
    broker = Broker(initial_cash=10000, fee_rate=0)

    broker.on_new_price("TEST", 100, "2026-01-01")
    order = broker.submit_market_order("TEST", qty=-1, price=100, stop_loss_price=110)
    assert order.status == "filled"
    assert broker.get_position_size("TEST") == -1
    # 开空 1 单位 @100，leverage=1: margin=100, cash=10000-100=9900
    assert approx(broker.get_cash()) == 9900

    # 价格涨到 110 → 触发止损
    broker.on_new_price("TEST", 110, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")

    assert broker.get_position_size("TEST") == 0
    # 平空 @110: realized_pnl = -1*(110-100) = -10, released_margin=100
    # cash = 9900 + 100 + (-10) = 9990
    assert approx(broker.get_cash()) == 9990


def test_short_take_profit_price_triggers_close():
    """空头止盈：开空 → 价格跌到止盈价 → 触发平仓。"""
    broker = Broker(initial_cash=10000, fee_rate=0)

    broker.on_new_price("TEST", 100, "2026-01-01")
    order = broker.submit_market_order("TEST", qty=-1, price=100, take_profit_price=90)
    assert order.status == "filled"
    assert broker.get_position_size("TEST") == -1
    assert approx(broker.get_cash()) == 9900

    # 价格跌到 90 → 触发止盈
    broker.on_new_price("TEST", 90, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")

    assert broker.get_position_size("TEST") == 0
    # 平空 @90: realized_pnl = -1*(90-100) = 10, released_margin=100
    # cash = 9900 + 100 + 10 = 10010
    assert approx(broker.get_cash()) == 10010


def test_short_take_profit_does_not_trigger_above_target():
    """空头止盈未到价不触发。"""
    broker = Broker(initial_cash=10000, fee_rate=0)

    broker.on_new_price("TEST", 100, "2026-01-01")
    broker.submit_market_order("TEST", qty=-1, price=100, take_profit_price=90)

    # 价格仍在止盈价上方
    broker.on_new_price("TEST", 95, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")

    assert broker.get_position_size("TEST") == -1


def test_short_stop_loss_does_not_trigger_below_target():
    """空头止损未到价不触发。"""
    broker = Broker(initial_cash=10000, fee_rate=0)

    broker.on_new_price("TEST", 100, "2026-01-01")
    broker.submit_market_order("TEST", qty=-1, price=100, stop_loss_price=110)

    # 价格仍在止损价下方
    broker.on_new_price("TEST", 105, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")

    assert broker.get_position_size("TEST") == -1


def test_short_trailing_stop_pct_triggers_on_rebound():
    """空头追踪止损 pct：开空 → 价格下跌（anchor 跟随最低价）→ 价格反弹到 anchor*(1+pct) → 触发。"""
    broker = Broker(initial_cash=10000, fee_rate=0)

    broker.on_new_price("TEST", 100, "2026-01-01")
    order = broker.submit_market_order("TEST", qty=-1, price=100, trailing_stop_pct=0.1)
    assert order.status == "filled"
    assert broker.get_position_size("TEST") == -1
    assert approx(broker.get_cash()) == 9900

    # 价格下跌到 80 → anchor=80, stop=80*1.1=88, 80 < 88 不触发
    broker.on_new_price("TEST", 80, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")
    assert broker.get_position_size("TEST") == -1

    # 价格反弹到 87 → anchor=min(80,87)=80, stop=88, 87 < 88 不触发
    broker.on_new_price("TEST", 87, "2026-01-03")
    broker.check_exit_rules(dt="2026-01-03")
    assert broker.get_position_size("TEST") == -1

    # 价格反弹到 89 → anchor=80, stop=88, 89 >= 88 触发
    broker.on_new_price("TEST", 89, "2026-01-04")
    broker.check_exit_rules(dt="2026-01-04")

    assert broker.get_position_size("TEST") == 0
    # 平空 @89: realized_pnl = -1*(89-100) = 11, released_margin=100
    # cash = 9900 + 100 + 11 = 10011
    assert approx(broker.get_cash()) == 10011


def test_short_trailing_stop_pct_anchor_follows_lowest():
    """空头追踪止损 anchor 跟随最低价：连续下跌不触发，反弹才触发。"""
    broker = Broker(initial_cash=10000, fee_rate=0)

    broker.on_new_price("TEST", 100, "2026-01-01")
    broker.submit_market_order("TEST", qty=-1, price=100, trailing_stop_pct=0.05)

    # 连续下跌，anchor 跟随下移
    broker.on_new_price("TEST", 90, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")
    assert broker.get_position_size("TEST") == -1

    broker.on_new_price("TEST", 80, "2026-01-03")
    broker.check_exit_rules(dt="2026-01-03")
    assert broker.get_position_size("TEST") == -1

    # anchor=80, stop=80*1.05=84, 价格反弹到 85 >= 84 触发
    broker.on_new_price("TEST", 85, "2026-01-04")
    broker.check_exit_rules(dt="2026-01-04")
    assert broker.get_position_size("TEST") == 0


# ===========================================================================
# 第三类：trailing_stop_amount 集成测试
# ===========================================================================

def test_long_trailing_stop_amount_triggers_on_pullback():
    """多头 trailing_stop_amount：开多 → 价格上涨（anchor 跟随最高价）→ 价格回落 amount → 触发。"""
    broker = Broker(initial_cash=10000, fee_rate=0)

    broker.on_new_price("TEST", 100, "2026-01-01")
    order = broker.submit_market_order("TEST", qty=1, price=100, trailing_stop_amount=5)
    assert order.status == "filled"
    assert broker.get_position_size("TEST") == 1
    # 开多 1 单位 @100: margin=100, cash=10000-100=9900
    assert approx(broker.get_cash()) == 9900

    # 价格涨到 105 → anchor=105, stop=105-5=100, 105 > 100 不触发
    broker.on_new_price("TEST", 105, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")
    assert broker.get_position_size("TEST") == 1

    # 价格回落到 102 → anchor=max(105,102)=105, stop=100, 102 > 100 不触发
    broker.on_new_price("TEST", 102, "2026-01-03")
    broker.check_exit_rules(dt="2026-01-03")
    assert broker.get_position_size("TEST") == 1

    # 价格回落到 99 → anchor=105, stop=100, 99 <= 100 触发
    broker.on_new_price("TEST", 99, "2026-01-04")
    broker.check_exit_rules(dt="2026-01-04")

    assert broker.get_position_size("TEST") == 0
    # 平多 @99: realized_pnl = 1*(99-100) = -1, released_margin=100
    # cash = 9900 + 100 + (-1) = 9999
    assert approx(broker.get_cash()) == 9999


def test_long_trailing_stop_amount_anchor_follows_highest():
    """多头 trailing_stop_amount anchor 跟随最高价：连续上涨不触发，回落才触发。"""
    broker = Broker(initial_cash=10000, fee_rate=0)

    broker.on_new_price("TEST", 100, "2026-01-01")
    broker.submit_market_order("TEST", qty=1, price=100, trailing_stop_amount=5)

    # 连续上涨，anchor 跟随上移
    broker.on_new_price("TEST", 110, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")
    assert broker.get_position_size("TEST") == 1

    broker.on_new_price("TEST", 120, "2026-01-03")
    broker.check_exit_rules(dt="2026-01-03")
    assert broker.get_position_size("TEST") == 1

    # anchor=120, stop=120-5=115, 价格回落到 114 <= 115 触发
    broker.on_new_price("TEST", 114, "2026-01-04")
    broker.check_exit_rules(dt="2026-01-04")
    assert broker.get_position_size("TEST") == 0


def test_short_trailing_stop_amount_triggers_on_rebound():
    """空头 trailing_stop_amount：开空 → 价格下跌（anchor 跟随最低价）→ 价格反弹 amount → 触发。"""
    broker = Broker(initial_cash=10000, fee_rate=0)

    broker.on_new_price("TEST", 100, "2026-01-01")
    order = broker.submit_market_order("TEST", qty=-1, price=100, trailing_stop_amount=5)
    assert order.status == "filled"
    assert broker.get_position_size("TEST") == -1
    assert approx(broker.get_cash()) == 9900

    # 价格跌到 95 → anchor=95, stop=95+5=100, 95 < 100 不触发
    broker.on_new_price("TEST", 95, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")
    assert broker.get_position_size("TEST") == -1

    # 价格反弹到 97 → anchor=min(95,97)=95, stop=100, 97 < 100 不触发
    broker.on_new_price("TEST", 97, "2026-01-03")
    broker.check_exit_rules(dt="2026-01-03")
    assert broker.get_position_size("TEST") == -1

    # 价格反弹到 101 → anchor=95, stop=100, 101 >= 100 触发
    broker.on_new_price("TEST", 101, "2026-01-04")
    broker.check_exit_rules(dt="2026-01-04")

    assert broker.get_position_size("TEST") == 0
    # 平空 @101: realized_pnl = -1*(101-100) = -1, released_margin=100
    # cash = 9900 + 100 + (-1) = 9999
    assert approx(broker.get_cash()) == 9999


def test_short_trailing_stop_amount_anchor_follows_lowest():
    """空头 trailing_stop_amount anchor 跟随最低价：连续下跌不触发，反弹才触发。"""
    broker = Broker(initial_cash=10000, fee_rate=0)

    broker.on_new_price("TEST", 100, "2026-01-01")
    broker.submit_market_order("TEST", qty=-1, price=100, trailing_stop_amount=10)

    # 连续下跌，anchor 跟随下移
    broker.on_new_price("TEST", 90, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")
    assert broker.get_position_size("TEST") == -1

    broker.on_new_price("TEST", 80, "2026-01-03")
    broker.check_exit_rules(dt="2026-01-03")
    assert broker.get_position_size("TEST") == -1

    # anchor=80, stop=80+10=90, 价格反弹到 91 >= 90 触发
    broker.on_new_price("TEST", 91, "2026-01-04")
    broker.check_exit_rules(dt="2026-01-04")
    assert broker.get_position_size("TEST") == 0