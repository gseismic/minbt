"""R8 回归：从交易意图、账户不变式和实际回放验证全量 Review 的缺陷。"""

from collections import OrderedDict
from datetime import timedelta

import pytest

from minbt import Bar, Broker, Exchange, Market, Strategy, markets
from minbt.broker.portfolio import Portfolio
from minbt.broker.struct import Position
from minbt.broker.exit import stop_loss_pct, take_profit_pct, stop_loss_price, take_profit_price
from minbt.data.model import datetime_key, normalize_datetime
from minbt.data.replay import BatchItem, TimeBatch


def _batch(dt, prices):
    """构造完整行情批次，确保多标的风险按一个截面结算。"""
    dt = normalize_datetime(dt)
    return TimeBatch(dt, tuple(
        BatchItem("prices", 0, 0, i, Bar(dt, symbol, "kline", {"close": price}))
        for i, (symbol, price) in enumerate(prices.items())
    ))


@pytest.mark.parametrize("symbols", [("A", "B"), ("B", "A")])
def test_cross_liquidation_settles_negative_position_equity_atomically(symbols):
    """R8-01：全仓可由另一持仓补足负权益，结算不能依赖建仓顺序。"""
    broker = Broker(1000, leverage=10)
    for symbol in symbols:
        assert broker.submit_market_order(symbol, 50, price=100).status == "filled"
    broker.process_market_batch(_batch("2026-01-01", {"A": 89, "B": 92}))

    assert broker.get_position_sizes() == {}
    assert broker.get_cash() == pytest.approx(50)
    assert broker.get_equity() == pytest.approx(50)
    assert broker.get_total_pnl().net_pnl == pytest.approx(-950)
    liquidations = [r for r in broker.get_pnl_records() if r.reason == "liquidation"]
    assert {r.symbol: r.realized_pnl for r in liquidations} == {"A": -550, "B": -400}


def test_failed_single_position_settlement_preserves_live_position_and_ledger():
    """R8-01：单仓释放负现金失败时，持仓与盈亏必须保持原状。"""
    portfolio = Portfolio(1000, 0, leverage=10, min_margin_level=0.01, warning_margin_level=0.02)
    for symbol in ("A", "B"):
        assert portfolio.submit_order(symbol, 50, 100)
    portfolio.update_market_batch({"A": 89, "B": 92})
    position = portfolio.get_position("A")
    before = (position.size, position.equity, portfolio.get_pnl(), portfolio.get_pnl_records())

    with pytest.raises(RuntimeError, match="free cash negative"):
        portfolio._pure_close_position("A")

    assert portfolio.get_position("A") is position
    assert (position.size, position.equity, portfolio.get_pnl(), portfolio.get_pnl_records()) == before
    assert portfolio.get_portfolio_equity() == 50


@pytest.mark.parametrize("method", ["close_position", "order_target_size", "order_target_value", "order_target_percent"])
def test_closing_intent_after_risk_liquidation_cannot_open_reverse_position(method):
    """R8-02：清仓所用数量必须取自价格风险推进后的实际仓位。"""
    broker = Broker(100)
    broker.submit_market_order("A", 1, price=100)
    args = () if method == "close_position" else (0,)
    order = getattr(broker, method)("A", *args, price=5)

    assert order.status == "skipped"
    assert broker.get_position_sizes() == {}
    assert broker.get_equity() == 5
    assert broker.get_total_pnl().net_pnl == -95
    assert [r.qty for r in broker.get_pnl_records()] == [1, -1]


def test_nonzero_target_percent_uses_equity_after_risk_settlement():
    """R8-02：比例目标也使用风险结算后的权益与持仓生成差额。"""
    broker = Broker(100)
    broker.submit_market_order("A", 1, price=100)
    order = broker.order_target_percent("A", 0.5, price=5)

    assert order.status == "filled"
    assert order.qty == 0.5
    assert broker.get_position_size("A") == 0.5
    assert broker.get_equity() == 5


def test_standalone_portfolio_close_also_rechecks_position_after_risk():
    """R8-02：独立 Portfolio 的全平入口不能在强平后反向开仓。"""
    portfolio = Portfolio(100, 0)
    portfolio.submit_order("A", 1, 100)
    portfolio.close_position("A", 5)
    assert portfolio.get_position_sizes() == {}
    assert portfolio.get_equity() == 5


@pytest.mark.parametrize("use_mark_price", [False, True])
def test_zero_quantity_portfolio_order_cannot_advance_price_or_liquidate(use_mark_price):
    """R8-06：独立 Portfolio 的零数量请求先拒绝，不能用其价格推进风险或写账。"""
    portfolio = Portfolio(100, 0)
    assert portfolio.submit_order("A", 1, 100)
    position = portfolio.get_position("A")
    before = (
        portfolio.last_prices.copy(), portfolio.last_prices_dt.copy(),
        portfolio.get_cash(), portfolio.get_equity(), portfolio.get_position_sizes(),
        portfolio.get_pnl(), portfolio.get_pnl_records(),
    )
    options = {"price": 100, "mark_price": 5} if use_mark_price else {"price": 5}
    assert portfolio.submit_order("A", 0, **options) is False
    assert portfolio.get_position("A") is position
    assert position.last_price == 100
    assert (
        portfolio.last_prices, portfolio.last_prices_dt,
        portfolio.get_cash(), portfolio.get_equity(), portfolio.get_position_sizes(),
        portfolio.get_pnl(), portfolio.get_pnl_records(),
    ) == before


@pytest.mark.parametrize("load_mode", ["preload", "incremental"])
def test_limit_fill_keeps_current_mark_in_final_result(load_mode):
    """R8-03：成本按限价，浮亏及最终结果按同批当前行情计算。"""
    class LimitBuyer(Strategy):
        def on_bars(self, dt, bars):
            if not self.broker.get_orders():
                self.broker.submit_limit_order("A", 1, 95)

    broker = Broker(1000)
    exchange = Exchange()
    exchange.set_bars([
        {"dt": "2026-01-01", "symbol": "A", "close": 100},
        {"dt": "2026-01-02", "symbol": "A", "close": 80},
    ])
    exchange.add_strategy(LimitBuyer("limit", broker))
    result = exchange.run(load_mode=load_mode)

    position = broker.get_position("A")
    assert (position.cost_price, position.last_price, broker.get_last_price("A")) == (95, 80, 80)
    assert [value for _, value in result.get_equity_curve()] == [1000, 985]
    assert result.get_total_pnl().net_pnl == -15
    assert result.get_orders()[0].avg_price == 95


def test_limit_fill_applies_risk_at_current_mark_in_same_batch():
    """R8-03：限价成交带来的浮亏立即结算风险，不等待下一根行情。"""
    broker = Broker(100, leverage=10)
    broker.on_new_price("A", 100)
    order = broker.submit_limit_order("A", 10, 95)
    broker.process_market_batch(_batch("2026-01-01", {"A": 80}))

    assert order.status == "filled"
    assert order.avg_price == 95
    assert broker.get_position_sizes() == {}
    assert broker.get_equity() == 0
    assert broker.get_total_pnl().net_pnl == -100


@pytest.mark.parametrize("sequence", [("A", "B"), ("B", "A")])
def test_close_portfolio_settles_all_fees_before_any_intermediate_risk(sequence):
    """R9-02：全平整体扣费，避免组内强平漏收手续费并改变顺序相关结果。"""
    broker = Broker(1270, fee_rate=0.01, leverage=10, min_margin_level=0.2, warning_margin_level=0.3)
    broker.add_portfolio("risk", 1260)
    for symbol in sequence:
        broker.submit_market_order(symbol, 1000 if symbol == "A" else 100,
                                   price=1 if symbol == "A" else 100, portfolio="risk")
    broker.process_market_batch(_batch("2026-01-01", {"A": 10, "B": 1}))
    assert broker.get_position_sizes("risk") == {"A": 1000, "B": 100}
    broker.process_market_batch(_batch("2026-01-02", {"OTHER": 100}))

    orders = broker.close_portfolio("risk")
    assert [order.status for order in orders] == ["filled", "filled"]
    assert broker.get_portfolios() == ["main"]
    assert broker.get_position_sizes() == {}
    assert broker.get_equity() == pytest.approx(159)
    assert broker.get_total_pnl().net_pnl == pytest.approx(-1111)
    assert [r.reason for r in broker.get_pnl_records()] == ["trade"] * 4
    # A/B 沿用旧报价，但手续费和风险结算实际发生在新回放批次。
    assert [r.dt for r in broker.get_pnl_records()[-2:]] == [normalize_datetime("2026-01-02")] * 2


@pytest.mark.parametrize("explicit_old_quote", [False, True])
def test_stale_quote_in_mixed_replay_cannot_bypass_weekend(explicit_old_quote):
    """R8-04：周六其他市场回调中下单，不能用周五报价时间通过休市检查。"""
    class WeekendBuyer(Strategy):
        def on_bars(self, dt, bars):
            if "BTC" in bars:
                options = {}
                if explicit_old_quote:
                    price, quote_dt = self.broker.get_last_price("A", return_dt=True)
                    options = {"price": price, "price_dt": quote_dt}
                self.order = self.broker.submit_market_order("A", 100, **options)

    broker = Broker(10000)
    broker.add_market("stock", markets.A_STOCK, ["A"])
    exchange = Exchange()
    exchange.set_bars([
        {"dt": "2026-01-09", "symbol": "A", "close": 10},
        {"dt": "2026-01-10", "symbol": "BTC", "close": 100},
    ])
    strategy = WeekendBuyer("weekend", broker)
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.order.status == "rejected"
    assert "not in trading time" in strategy.order.reason
    assert strategy.order.updated_dt == normalize_datetime("2026-01-10")
    assert broker.get_position_sizes() == {}


@pytest.mark.parametrize("explicit_old_quote", [False, True])
def test_stale_quote_t_plus_one_locks_by_actual_fill_day(explicit_old_quote):
    """R8-04：周二按周一旧价买入仍锁到周三，记录也采用周二成交时间。"""
    bought = normalize_datetime("2026-01-06T01:30:00Z")
    same_day = bought + timedelta(minutes=1)
    next_day = bought + timedelta(days=1)

    class DailyBuyer(Strategy):
        def on_bars(self, dt, bars):
            if dt == bought:
                options = {}
                if explicit_old_quote:
                    price, quote_dt = self.broker.get_last_price("A", return_dt=True)
                    options = {"price": price, "price_dt": quote_dt}
                self.buy = self.broker.submit_market_order("A", 100, **options)
            elif dt == same_day:
                self.sell = self.broker.close_position("A")
                self.locked = self.broker.get_position("A").locked_size
            elif dt == next_day:
                self.final_sell = self.broker.close_position("A")

    broker = Broker(10000)
    broker.add_market("stock", markets.A_STOCK, ["A"])
    exchange = Exchange()
    exchange.set_bars([
        {"dt": "2026-01-05", "symbol": "A", "close": 10},
        *({"dt": dt, "symbol": "BTC", "close": 100} for dt in (bought, same_day, next_day)),
    ])
    strategy = DailyBuyer("t1", broker)
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.buy.updated_dt == bought
    assert broker.get_pnl_records(order_id=strategy.buy.id)[0].dt == bought
    assert strategy.sell.status == "rejected"
    assert strategy.locked == 100
    assert strategy.final_sell.status == "filled"
    assert broker.get_position_sizes() == {}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, "100"])
@pytest.mark.parametrize("argument", ["price", "qty", "leverage", "target_size", "target_value", "target_percent"])
def test_invalid_trade_numbers_do_not_modify_account(argument, value):
    """R8-06：校验先于报价风险推进，非法订单不能清掉原空头或修改账本。"""
    broker = Broker(1000)
    broker.submit_market_order("A", -1, price=100)
    before = (broker.last_prices.copy(), broker.get_equity(), broker.get_position_sizes(), broker.get_pnl_records())
    if argument.startswith("target_"):
        method = getattr(broker, "order_" + argument)
        options = {argument: value, "price": 5000}
    else:
        method = broker.submit_market_order
        options = {"qty": 1, "price": 5000, argument: value}

    with pytest.raises((ValueError, TypeError)):
        method("A", **options)

    assert (broker.last_prices, broker.get_equity(), broker.get_position_sizes(), broker.get_pnl_records()) == before
    assert len(broker.get_orders()) == 1


@pytest.mark.parametrize("field", ["stop_loss_price", "take_profit_price", "trailing_stop_pct", "trailing_stop_amount"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_invalid_exit_numbers_preserve_existing_protection(field, value):
    """R8-06：无效保护值不能随显式价格推进账户，也不能污染原退出配置。"""
    broker = Broker(1000)
    entry = broker.submit_market_order("A", 1, price=100, stop_loss_price=90)
    before = broker.get_exit(entry.id)
    with pytest.raises((ValueError, TypeError)):
        broker.submit_market_order("A", 1, price=5, **{field: value})
    with pytest.raises((ValueError, TypeError)):
        broker.set_exit(entry.id, **{field: value})
    assert broker.get_exit(entry.id) == before
    assert broker.get_last_price("A") == 100
    assert broker.get_position_size("A") == 1


@pytest.mark.parametrize("field", ["initial_cash", "leverage", "fee_rate", "warning_margin_level", "min_margin_level"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_account_configuration_requires_finite_numbers(field, value):
    """R8-06：初始资金、杠杆和风险配置不能以非有限数值创建账户。"""
    options = {"initial_cash": 1000, field: value}
    with pytest.raises((ValueError, TypeError)):
        Broker(**options)
    with pytest.raises((ValueError, TypeError)):
        Portfolio(**{"fee_rate": 0, **options})


@pytest.mark.parametrize("field", ["price", "qty", "leverage"])
def test_invalid_reversal_parameters_cannot_clear_standalone_position(field):
    """R8-06：Position 反手的两段提交之前也要完成校验，非法新开不能先清掉旧仓。"""
    position = Position("A")
    position.commit_order(100, 1, 1)
    options = {"price": 100, "qty": -2, "leverage": 1, field: float("nan")}
    with pytest.raises(ValueError, match="finite"):
        position.commit_order(**options)
    assert position.size == 1
    assert position.cost_price == 100
    assert position.margin == 100


@pytest.mark.parametrize("factory", [stop_loss_pct, take_profit_pct, stop_loss_price, take_profit_price])
def test_exit_factory_rejects_non_finite_threshold(factory):
    """R8-06：独立函数规则工厂也不能创建永远不触发的 NaN 条件。"""
    with pytest.raises(ValueError, match="finite"):
        factory(float("nan"))


def test_invalid_limit_and_price_update_numbers_preserve_account():
    """R8-06：挂单、报价更新和资金划拨均在非法参数前保持无副作用。"""
    broker = Broker(1000)
    broker.submit_market_order("A", -1, price=100)
    before = (broker.last_prices.copy(), broker.get_position_sizes(), broker.get_total_pnl(), broker.get_pnl_records())
    for action in (
        lambda: broker.submit_limit_order("A", 1, float("inf")),
        lambda: broker.on_new_price("A", float("inf"), "2026-01-02"),
        lambda: broker.add_portfolio("bad", float("nan")),
    ):
        with pytest.raises(ValueError, match="finite"):
            action()
    assert (broker.last_prices, broker.get_position_sizes(), broker.get_total_pnl(), broker.get_pnl_records()) == before
    assert len(broker.get_orders()) == 1
    assert broker.get_portfolios() == ["main"]


def test_exit_merge_preserves_custom_rule_state_across_order_handles():
    """R8-07：加仓和旧句柄再次修改都保留规则对象与已有 state。"""
    broker = Broker(1000)
    first = broker.submit_market_order("A", 1, price=100, stop_loss_price=90, trailing_stop_amount=5)

    def after_three_checks(ctx):
        ctx.state["checks"] = ctx.state.get("checks", 0) + 1
        return ctx.state["checks"] == 3

    rule = broker.add_exit(first.id, name="three", condition=after_three_checks)
    broker.check_exit_rules()
    second = broker.submit_market_order("A", 1, price=100, stop_loss_price=95)
    assert broker.get_exit(second.id).custom_rules == ("three",)
    assert broker.get_exit(second.id).trailing_anchor == 100
    broker.check_exit_rules()
    config = broker.set_exit(first.id, take_profit_price=120)
    assert config.stop_loss_price == 95
    assert config.trailing_stop_amount == 5
    assert config.custom_rules == ("three",)
    assert rule.state == {"checks": 2}
    broker.check_exit_rules()
    assert rule.state == {"checks": 3}
    assert broker.get_position_size("A") == 0


def test_exit_updates_and_selective_clear_merge_on_any_current_order():
    """R8-07：换订单增加止盈或函数条件，不得移除止损；旧句柄可选择性清除。"""
    broker = Broker(1000)
    first = broker.submit_market_order("A", 1, price=100, stop_loss_price=90)
    second = broker.submit_market_order("A", 1, price=100)
    broker.set_exit(second.id, take_profit_price=120)
    broker.add_exit(first.id, condition=lambda ctx: False, name="keep")
    cleared = broker.clear_exit(second.id, stop_loss_price=False, take_profit_price=True, trailing_stop=False, custom=False)
    assert cleared.stop_loss_price == 90
    assert cleared.take_profit_price is None
    assert cleared.custom_rules == ("keep",)
    broker.on_new_price("A", 85)
    broker.check_exit_rules()
    assert broker.get_position_size("A") == 0


def test_risk_liquidation_expires_rules_before_reopening():
    """R8-07：即使没有调用 check_exit_rules，强平也已结束旧保护生命周期。"""
    broker = Broker(100)
    first = broker.submit_market_order("A", 1, price=100, stop_loss_price=90)
    broker.add_exit(first.id, condition=lambda ctx: True)
    broker.on_new_price("A", 5)
    second = broker.submit_market_order("A", 0.5, price=5, take_profit_price=6)
    assert broker.get_exit(first.id).active is False
    assert broker.get_exit(second.id).custom_rules == ()
    assert broker.get_exit(second.id).stop_loss_price is None
    with pytest.raises(ValueError, match="no longer associated"):
        broker.clear_exit(first.id)


@pytest.mark.parametrize("symbol", ["abc", " abc "])
def test_symbol_identity_is_shared_by_replay_orders_and_queries(symbol):
    """R8-09：相同输入在行情和账户中使用一个标识，行情上涨正确计浮盈。"""
    class Holder(Strategy):
        def on_bars(self, dt, bars):
            self.broker.order_target_size(symbol, 1, price=bars["ABC"]["close"])

    broker = Broker(1000)
    exchange = Exchange()
    exchange.set_bars([
        {"dt": "2026-01-01", "symbol": symbol, "close": 100},
        {"dt": "2026-01-02", "symbol": symbol, "close": 120},
    ])
    holder = Holder("holder", broker)
    exchange.add_strategy(holder)
    result = exchange.run()
    assert broker.get_position_sizes() == {"ABC": 1}
    assert broker.get_position(symbol).last_price == 120
    assert broker.get_pnl(symbol).net_pnl == 20
    assert broker.get_total_pnl(symbol).net_pnl == 20
    assert broker.get_pnl_records(symbol=symbol)[0].symbol == "ABC"
    assert len(broker.get_orders(symbol=symbol)) == 2
    assert [value for _, value in result.get_equity_curve()] == [1000, 1020]
    assert [size for _, size in result.get_position_curve(symbol)] == [1, 1]
    assert holder.get_hist_position_sizes(symbol) == [1, 1]


def test_market_routes_normalize_symbols_and_check_duplicates():
    """R8-09：小写路由仍应用 A 股禁空与整手约束，归一化后不能重复绑定。"""
    broker = Broker(10000)
    with pytest.raises(ValueError, match="duplicate"):
        broker.add_market("stock", markets.A_STOCK, ["abc", " ABC "])
    broker.add_market("stock", markets.A_STOCK, [" abc "])
    assert broker.get_market("abc").name == "stock"
    assert broker.submit_market_order("ABC", -100, price=10, price_dt="2026-01-05").status == "rejected"
    assert broker.submit_market_order("abc", 1, price=10).status == "rejected"
    assert broker.get_position_sizes() == {}


@pytest.mark.parametrize("t_plus", [0, 1])
@pytest.mark.parametrize("length", [200, 400])
def test_target_strategy_does_not_scan_historical_orders_each_batch(t_plus, length):
    """R8-10：真实目标仓位循环保留 skipped 日志，但推进行情不遍历历史订单。"""
    class CountedOrders(OrderedDict):
        """统计历史订单访问量，用复杂度断言避免不稳定的耗时阈值。"""
        visits = 0

        def values(self):
            for order in super().values():
                self.visits += 1
                yield order

    broker = Broker(1000, market=Market(t_plus=t_plus))
    broker.orders = CountedOrders()
    start = normalize_datetime("2026-01-01")
    for index in range(length):
        broker.process_market_batch(_batch(start + timedelta(minutes=index), {"A": 100}))
        broker.order_target_size("A", 1)
    assert len(broker.orders) == length
    assert broker.orders.visits == 0
    assert broker.get_position_size("A") == 1


@pytest.mark.parametrize("load_mode", ["preload", "incremental"])
def test_adjacent_milliseconds_remain_distinct_in_replay(load_mode):
    """R8-14：2039 年的相邻毫秒不能因浮点截断碰撞或误报重复行情。"""
    first = normalize_datetime("2039-01-01T00:00:00.001Z")
    second = normalize_datetime("2039-01-01T00:00:00.002Z")
    assert datetime_key(first) == 2177452800001
    assert datetime_key(second) == 2177452800002

    class Observer(Strategy):
        def on_init(self):
            self.times = []

        def on_bars(self, dt, bars):
            self.times.append(dt)

    exchange = Exchange()
    exchange.set_bars([
        {"dt": first, "symbol": "A", "close": 100},
        {"dt": second, "symbol": "A", "close": 101},
    ])
    observer = Observer("milliseconds")
    exchange.add_strategy(observer)
    exchange.run(load_mode=load_mode)
    assert observer.times == [first, second]
