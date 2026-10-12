"""验证受控运行的真实账户变化、生命周期、结果隔离与资源释放。"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event

import pytest

from minbt import Bar, Broker, Exchange, RunResult, Strategy
from minbt.protocols.broker import BROKER_PROTOCOL_METHODS


def dt(minute):
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minute)


class Feed:
    """有序有限来源，同时观测 Feed 和事件迭代器的释放。"""

    name = "prices"
    ordered = supports_preload = supports_incremental = replayable = True

    def __init__(self, prices):
        self.prices = prices
        self.prepared = self.closed = self.iterator_closed = 0

    def prepare(self):
        self.prepared += 1

    def events(self):
        try:
            for minute, price in enumerate(self.prices):
                yield Bar(dt(minute), "A", "kline", {"close": price})
        finally:
            self.iterator_closed += 1

    def close(self):
        self.closed += 1


class BuyAndHold(Strategy):
    """首次收到行情时买一份，持仓的真实估值用于独立手算。"""

    def __init__(self, strategy_id="hold", broker=None):
        super().__init__(strategy_id, broker)
        self.initializations = self.finishes = 0
        self.seen = []

    def on_init(self):
        self.initializations += 1

    def on_bars(self, current_dt, bars):
        if not self.seen and self.broker is not None:
            self.broker.submit_market_order("A", qty=1)
        self.seen.append(current_dt)

    def on_finish(self):
        self.finishes += 1


def setup(prices=(100, 110, 90, 120, 999), *, broker=None, strategy_type=BuyAndHold, feed=None):
    broker = Broker(initial_cash=1000) if broker is None else broker
    strategy = strategy_type(broker=broker)
    feed = Feed(prices) if feed is None else feed
    exchange = Exchange()
    exchange.add_feed(feed)
    exchange.add_strategy(strategy)
    return exchange, strategy, broker, feed


@pytest.mark.parametrize("mode", ["auto", "preload", "incremental"])
def test_pause_continue_exit_preserve_real_account_curve(mode):
    """暂停期间有持仓盈亏；退出不能把已预读的 999 价格算入账户。"""
    exchange, strategy, broker, feed = setup()
    commands = iter(("continue", "pause", "pause", "continue", "exit"))
    boundaries = []

    def control():
        boundaries.append(exchange.get_current_dt())
        return next(commands)

    result = exchange.run(control=control, load_mode=mode)

    assert isinstance(result, RunResult)
    assert strategy.seen == [dt(0), dt(3)]
    assert boundaries == [None, dt(0), dt(1), dt(2), dt(3)]
    assert result.get_equity_curve() == list(zip(map(dt, range(4)), (1000, 1010, 990, 1020)))
    assert result.get_position_curve("A") == [(dt(i), 1) for i in range(4)]
    assert strategy.get_hist_equity() == [1000, 1010, 990, 1020]
    assert result.get_position_sizes() == {"A": 1}
    assert result.get_initial_cash() == 1000
    assert result.get_total_pnl().net_pnl == 20
    assert broker.get_last_price("A") == 120
    assert result.meta == {
        "status": "exited", "reason": "control_exit", "control_state": "exit",
        "start": None, "end": None, "first_dt": dt(0), "last_dt": dt(3),
        "step_count": 4, "strategy_ids": ("hold",),
        "control_events": ((dt(0), 1, "pause"), (dt(2), 3, "continue"), (dt(3), 4, "exit")),
    }
    assert strategy.initializations == strategy.finishes == 1
    assert feed.closed == feed.iterator_closed == 1


@pytest.mark.parametrize("mode", ["preload", "incremental"])
def test_window_filters_before_control_and_account_processing(mode):
    """UTC 窗口与账户推进一致，端点外的价格和控制回调不能生效。"""
    exchange, strategy, broker, feed = setup(prices=(1, 100, 200, 300))
    checks = []
    result = exchange.run(
        start="2026-01-01T01:01:00+01:00",
        end=datetime(2026, 1, 1, 0, 3),
        control=lambda: checks.append(exchange.get_current_dt()) or "continue",
        load_mode=mode,
    )

    assert checks == [None, dt(1)]
    assert strategy.seen == [dt(1), dt(2)]
    assert result.get_equity_curve() == [(dt(1), 1000), (dt(2), 1100)]
    assert broker.get_last_price("A") == 200
    assert result.meta["start"] == result.meta["first_dt"] == dt(1)
    assert result.meta["end"] == dt(3)
    assert result.meta["last_dt"] == dt(2)
    assert result.meta["reason"] == "end_reached"
    assert result.meta["step_count"] == 2
    assert feed.closed == feed.iterator_closed == 1


@pytest.mark.parametrize("bounds,minutes,reason", [
    ({}, [0, 1, 2], "feed_exhausted"),
    ({"start": dt(1)}, [1, 2], "feed_exhausted"),
    ({"end": dt(2)}, [0, 1], "end_reached"),
    ({"end": dt(9)}, [0, 1, 2], "feed_exhausted"),
])
def test_default_and_single_sided_windows_include_last_available_data(bounds, minutes, reason):
    """None 使用自然数据边界，请求终点比数据晚时不能冒充已到达终点。"""
    exchange, strategy, _, _ = setup(prices=(100, 101, 102))
    result = exchange.run(**bounds)
    assert strategy.seen == list(map(dt, minutes))
    assert result.meta["status"] == "completed"
    assert result.meta["reason"] == reason
    assert result.meta["control_events"] == ()
    assert result.meta["control_state"] == "continue"


@pytest.mark.parametrize("mode", ["preload", "incremental"])
def test_initial_exit_returns_empty_progress_and_real_initial_account(mode):
    """第一批前退出应保留账户信息，并与空来源错误区分。"""
    exchange, strategy, broker, feed = setup()
    result = exchange.run(control=lambda: "exit", load_mode=mode)
    assert result.meta["status"] == "exited"
    assert result.meta["first_dt"] is result.meta["last_dt"] is None
    assert result.meta["step_count"] == 0
    assert result.meta["control_events"] == ((None, 0, "exit"),)
    assert result.get_equity_curve() == result.get_position_curve("A") == result.get_orders() == []
    assert result.get_initial_cash() == 1000
    assert result.get_total_pnl().net_pnl == 0
    assert broker.get_last_price("A") is None
    assert strategy.initializations == strategy.finishes == 1
    assert feed.closed == feed.iterator_closed == 1


def test_paused_run_can_naturally_complete_without_strategy_market_callbacks():
    """自然结束状态与最后的暂停状态独立，初始化和结束仍各通知一次。"""
    exchange, strategy, _, _ = setup(prices=(100, 110))
    result = exchange.run(control=lambda: "pause")
    assert strategy.seen == []
    assert strategy.initializations == strategy.finishes == 1
    assert result.meta["status"] == "completed"
    assert result.meta["control_state"] == "pause"
    assert result.meta["control_events"] == ((None, 0, "pause"),)
    assert result.get_equity_curve() == [(dt(0), 1000), (dt(1), 1000)]


def test_pending_order_and_stop_loss_continue_during_pause():
    """暂停策略不冻结挂单撮合或止损，持仓曲线必须记录这两次变化。"""
    class LimitStrategy(BuyAndHold):
        def on_bars(self, current_dt, bars):
            self.broker.submit_limit_order("A", qty=1, limit_price=95, stop_loss_price=90)
            self.seen.append(current_dt)

    exchange, strategy, _, _ = setup((100, 95, 85, 999), strategy_type=LimitStrategy)
    commands = iter(("continue", "pause", "pause", "exit"))
    result = exchange.run(control=lambda: next(commands))
    assert strategy.seen == [dt(0)]
    assert result.get_equity_curve() == [(dt(0), 1000), (dt(1), 1000), (dt(2), 990)]
    assert result.get_position_curve("A") == [(dt(0), 0), (dt(1), 1), (dt(2), 0)]
    orders = result.get_orders()
    assert [order.status for order in orders] == ["filled", "filled"]
    assert orders[0].created_dt == dt(0) and orders[0].updated_dt == dt(1)
    assert orders[1].updated_dt == dt(2)
    assert result.get_total_pnl().realized_pnl == -10


def test_exit_retains_pending_order_and_freezes_it_before_later_fill():
    """受控退出不撤单，原订单之后成交也不能改写退出点的订单快照。"""
    class PendingStrategy(BuyAndHold):
        def on_bars(self, current_dt, bars):
            self.broker.submit_limit_order("A", qty=1, limit_price=95)

    exchange, _, broker, _ = setup((100, 95, 80), strategy_type=PendingStrategy)
    commands = iter(("continue", "exit"))
    result = exchange.run(control=lambda: next(commands))
    assert result.get_equity_curve() == [(dt(0), 1000)]
    pending = result.get_orders()[0]
    assert pending.status == "pending" and pending.filled_qty == 0
    assert broker.get_orders()[0].status == "pending"
    assert result.get_position_sizes() == {}
    broker.on_new_price("A", 95, dt(1))
    broker.process_pending_orders(dt(1))
    assert broker.get_orders()[0].status == "filled"
    assert pending.status == "pending" and result.get_position_sizes() == {}


def test_custom_exit_rule_runs_while_strategy_is_paused():
    """函数型账户规则仍属 Broker，不因策略指标回调暂停而停止。"""
    checks = []

    class ExitStrategy(BuyAndHold):
        def on_bars(self, current_dt, bars):
            super().on_bars(current_dt, bars)
            order = self.broker.get_orders()[0]

            def condition(ctx):
                checks.append(ctx.price)
                return ctx.price < 90

            self.broker.add_exit(order.id, condition=condition)

    exchange, _, _, _ = setup((100, 110, 80), strategy_type=ExitStrategy)
    commands = iter(("continue", "pause", "pause"))
    result = exchange.run(control=lambda: next(commands))
    assert checks == [110, 80]
    assert result.get_total_pnl().net_pnl == -20
    assert result.get_position_curve("A")[-1] == (dt(2), 0)


@pytest.mark.parametrize("mode,qty,price,final_equity", [
    ("isolated", 10, 91, 909),
    ("isolated", 10, 80, 899),
    ("cross", 50, 81, 45),
    ("cross", 50, 79, 0),
])
def test_paused_accounts_still_liquidate_or_settle_bankruptcy(mode, qty, price, final_equity):
    """强平与穿仓结算在暂停期间仍发生，曲线必须包含手续费和风险损失。"""
    class Leveraged(BuyAndHold):
        def on_bars(self, current_dt, bars):
            self.broker.submit_market_order("A", qty=qty)
            self.seen.append(current_dt)

    broker = Broker(initial_cash=1000, fee_rate=0.001, leverage=10, margin_mode=mode)
    exchange, strategy, _, _ = setup((100, price), broker=broker, strategy_type=Leveraged)
    commands = iter(("continue", "pause"))
    result = exchange.run(control=lambda: next(commands))
    assert strategy.seen == [dt(0)]
    assert result.get_equity_curve() == [(dt(0), 1000 - qty * 0.1), (dt(1), final_equity)]
    assert result.get_position_curve("A")[-1] == (dt(1), 0)
    assert result.get_total_pnl().net_pnl == final_equity - 1000


def test_all_callbacks_and_shared_broker_use_one_state_per_complete_timestamp():
    """多个标的、来源和策略共用一次检查，共享账户每个时间点只推进一次。"""
    class CountingBroker(Broker):
        def __init__(self):
            super().__init__(initial_cash=1000)
            self.batches = []

        def process_market_batch(self, batch):
            self.batches.append(batch.dt)
            return super().process_market_batch(batch)

    class Probe(Strategy):
        def on_init(self):
            self.calls = []

        def on_bars(self, current_dt, bars):
            self.calls.append((current_dt, "bars", tuple(bars)))

        def on_books(self, current_dt, books):
            self.calls.append((current_dt, "books"))

        def on_trades(self, current_dt, trades):
            self.calls.append((current_dt, "trades"))

        def on_bar(self, current_dt, bar):
            self.calls.append((current_dt, "bar"))

        def on_news(self, current_dt, news):
            self.calls.append((current_dt, "news"))

    class Signals(Feed):
        name = "signals"

        def events(self):
            for minute in range(3):
                yield Bar(dt(minute), "A", "signal", {"value": 1})

    exchange = Exchange()
    exchange.set_bars([{"dt": dt(i), "symbol": symbol, "close": 100} for i in range(3) for symbol in ("A", "B")])
    exchange.set_books([{"dt": dt(i), "symbol": "A", "mid": 101} for i in range(3)])
    exchange.set_trades([{"dt": dt(i), "symbol": "A", "price": 102} for i in range(3)])
    exchange.set_news([{"dt": dt(i), "headline": "event"} for i in range(3)])
    exchange.add_feed(Signals(()))
    broker = CountingBroker()
    first, second = Probe("one", broker), Probe("two", broker)
    exchange.add_strategy(first)
    exchange.add_strategy(second)
    commands = iter(("pause", "continue", "exit"))
    result = exchange.run(control=lambda: next(commands))
    assert broker.batches == [dt(0), dt(1)]
    assert first.calls == second.calls == [(dt(1), "bars", ("A", "B")), (dt(1), "books"), (dt(1), "trades"), (dt(1), "bar"), (dt(1), "news")]
    with pytest.raises(ValueError, match="strategy_id"):
        result.get_equity_curve()
    assert result.get_equity_curve(strategy_id="one") == result.get_equity_curve(strategy_id="two")
    assert first.get_hist_equity() == second.get_hist_equity() == [1000, 1000]


@pytest.mark.parametrize("bad", [None, True, 1, [], {}, "resume"])
def test_invalid_control_result_fails_and_consumes_lifecycle(bad):
    """错误的控制返回值不能被解释为继续或包装成正常完成。"""
    exchange, strategy, _, feed = setup()
    with pytest.raises(ValueError, match="control must return"):
        exchange.run(control=lambda: bad)
    assert strategy.initializations == 1 and strategy.finishes == 0
    assert feed.closed == feed.iterator_closed == 1
    with pytest.raises(RuntimeError, match="only be run once"):
        exchange.run()


@pytest.mark.parametrize("arguments,error", [
    ({"start": dt(2), "end": dt(1)}, ValueError),
    ({"start": dt(1), "end": dt(1)}, ValueError),
    ({"start": "not a date"}, ValueError),
    ({"control": "pause"}, TypeError),
    ({"load_mode": "bad"}, ValueError),
])
def test_startup_validation_can_be_corrected_before_consuming_instances(arguments, error):
    """启动前参数错误不消耗对象，允许修正后运行同一配置。"""
    exchange, strategy, _, feed = setup()
    with pytest.raises(error):
        exchange.run(**arguments)
    assert feed.prepared == strategy.initializations == 0
    assert exchange.run().meta["status"] == "completed"


@pytest.mark.parametrize("prices,bounds", [((), {}), ((100, 110), {"start": dt(9)}), ((100, 110), {"end": dt(0)})])
def test_empty_window_raises_and_closes_resources(prices, bounds):
    """无实际数据不是成功回测，且已开始读取的对象不能重试。"""
    exchange, strategy, _, feed = setup(prices)
    with pytest.raises(ValueError, match="no data"):
        exchange.run(**bounds)
    assert strategy.finishes == 0
    assert feed.closed == feed.iterator_closed == 1
    with pytest.raises(RuntimeError):
        exchange.run()


def test_native_instances_cannot_be_reused_but_unstarted_setup_can_be_corrected():
    """仅新建 Exchange 不能清除旧账户，占用失败不能污染新的策略。"""
    exchange, strategy, broker, _ = setup((100, 110))
    exchange.run()
    another, fresh, _, feed = setup((100, 110), broker=broker)
    with pytest.raises(RuntimeError, match="already been used"):
        Exchange().add_strategy(strategy)
    with pytest.raises(RuntimeError, match="Broker has already been used"):
        another.run()
    assert feed.prepared == fresh.initializations == 0
    fresh.set_broker(Broker(initial_cash=1000))
    assert another.run().meta["status"] == "completed"
    with pytest.raises(RuntimeError, match="only be run once"):
        exchange.run()


def test_concurrent_exchanges_cannot_claim_the_same_account():
    """不同 Exchange 同时启动时，共享账户只能归属其中一个实验。"""
    broker = Broker(initial_cash=1000)
    first, _, _, _ = setup((100, 110), broker=broker)
    second, _, _, _ = setup((100, 110), broker=broker)
    barrier = Barrier(2)

    def run(exchange):
        barrier.wait(timeout=5)
        try:
            return exchange.run().meta["status"]
        except RuntimeError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outputs = list(executor.map(run, (first, second)))
    assert outputs.count("completed") == 1
    assert sum("Broker has already been used" in output for output in outputs) == 1


def test_same_exchange_has_only_one_concurrent_start():
    """同一个运行入口并发启动时，只能有一次生命周期和一次交易。"""
    exchange, strategy, _, _ = setup((100, 110))
    barrier = Barrier(2)

    def run():
        barrier.wait(timeout=5)
        try:
            return exchange.run().meta["status"]
        except RuntimeError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outputs = list(executor.map(lambda _: run(), range(2)))
    assert sorted(outputs) == ["completed", "rejected"]
    assert strategy.initializations == strategy.finishes == 1


def test_external_thread_cannot_trade_during_market_callback():
    """运行线程处理市场时，外部控制线程不能直接写账户。"""
    entered, release = Event(), Event()
    exchange, strategy, broker, _ = setup((100, 110))
    original = strategy.on_bars

    def callback(current_dt, bars):
        entered.set()
        assert release.wait(timeout=5)
        original(current_dt, bars)

    strategy.on_bars = callback
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(exchange.run)
        try:
            assert entered.wait(timeout=5)
            with pytest.raises(RuntimeError, match="run thread"):
                broker.submit_market_order("A", qty=1, price=100)
        finally:
            release.set()
        assert running.result(timeout=5).meta["status"] == "completed"


def test_result_remains_immutable_after_account_and_returned_containers_change():
    """旧结果与账户、原订单以及查询返回容器分别隔离。"""
    exchange, _, broker, _ = setup((100, 110))
    broker.add_portfolio("other", cash=200)
    result = exchange.run()
    expected = [(dt(0), 1000), (dt(1), 1010)]
    curve = result.get_equity_curve()
    curve.clear()
    positions = result.get_position_sizes()
    positions["A"] = 99
    orders = result.get_orders()
    with pytest.raises(FrozenInstanceError):
        orders[0].qty = 99
    with pytest.raises(TypeError):
        result.meta["status"] = "completed"
    with pytest.raises(FrozenInstanceError):
        result.meta = {}
    broker.get_orders()[0].avg_price = 999
    broker.on_new_price("A", 120, dt(2))
    broker.submit_market_order("A", qty=1)
    assert result.get_equity_curve() == expected
    assert result.get_orders()[0].avg_price == 100
    assert len(result.get_orders()) == 1
    assert result.get_position_sizes() == {"A": 1}
    assert result.get_position_sizes(portfolio="other") == {}
    assert result.get_position_curve("NEVER") == [(dt(0), 0), (dt(1), 0)]
    assert result.get_total_pnl().net_pnl == 10
    with pytest.raises(ValueError):
        result.get_position_sizes(portfolio="missing")
    with pytest.raises(ValueError):
        result.get_orders(strategy_id="missing")


@pytest.mark.parametrize("optional_stubs", [False, True])
def test_custom_broker_only_requires_the_existing_protocol(optional_stubs):
    """协议外的数据能力缺失时明确报错，不给出伪造的零订单或盈亏。"""
    class CustomBroker:
        def __init__(self):
            backing = Broker(initial_cash=1000)
            for name in (*BROKER_PROTOCOL_METHODS, "process_market_batch"):
                if name != "get_position_sizes":
                    setattr(self, name, getattr(backing, name))
            self._positions = backing.get_position_sizes
            if optional_stubs:
                for name in ("get_portfolios", "get_orders", "get_total_pnl"):
                    setattr(self, name, self.unsupported)

        def get_position_sizes(self, portfolio=None):
            if portfolio is not None:
                raise NotImplementedError("only the default portfolio is supported")
            return self._positions()

        def unsupported(self):
            raise NotImplementedError("optional data is not available")

    exchange, _, _, _ = setup((100, 110), broker=CustomBroker())
    result = exchange.run()
    assert result.get_equity_curve() == [(dt(0), 1000), (dt(1), 1010)]
    assert result.get_position_sizes() == {"A": 1}
    for query in (result.get_initial_cash, result.get_orders, result.get_total_pnl):
        with pytest.raises(NotImplementedError):
            query()
    with pytest.raises(NotImplementedError):
        result.get_position_sizes(portfolio="other")


def test_strategy_without_broker_returns_progress_but_no_fake_account():
    """纯信号策略可返回运行信息，账户查询必须说明没有 Broker。"""
    exchange = Exchange()
    exchange.set_bars([{"dt": dt(0), "symbol": "A", "close": 100}])
    exchange.add_strategy(Strategy("signal"))
    result = exchange.run()
    assert result.meta["step_count"] == 1
    with pytest.raises(ValueError, match="no Broker"):
        result.get_equity_curve()


def test_missing_configuration_can_be_supplied_before_start():
    """缺少来源或策略的校验失败不会提前消耗启动权。"""
    exchange = Exchange()
    with pytest.raises(ValueError, match="data is not set"):
        exchange.run()
    exchange.set_bars([{"dt": dt(0), "symbol": "A", "close": 100}])
    with pytest.raises(ValueError, match="no strategies"):
        exchange.run()
    exchange.add_strategy(Strategy("signal"))
    assert exchange.run().meta["status"] == "completed"


@pytest.mark.parametrize("phase", ["control", "on_finish"])
def test_control_and_finish_cannot_trade_or_reprice_account(phase):
    """结果边界不能被控制函数或报告阶段的额外交易改变。"""
    exchange, strategy, broker, feed = setup((100, 110))
    if phase == "control":
        def callback():
            return broker.on_new_price("A", 999)
    else:
        strategy.on_finish = lambda: broker.close_position("A")
        callback = None
    with pytest.raises(RuntimeError, match=f"read-only during {phase}"):
        exchange.run(control=callback)
    assert feed.closed == feed.iterator_closed == 1
    assert broker._run_readonly is None


@pytest.mark.parametrize("operation", [
    lambda e, s: e.run(),
    lambda e, s: e.set_bars([]),
    lambda e, s: e.set_books([]),
    lambda e, s: e.set_trades([]),
    lambda e, s: e.set_news([]),
    lambda e, s: e.add_feed(Feed(())),
    lambda e, s: e.add_strategy(Strategy("new")),
    lambda e, s: e.remove_strategy(s.strategy_id),
    lambda e, s: s.set_broker(Broker(initial_cash=1000)),
    lambda e, s: setattr(s, "broker", None),
    lambda e, s: s.set_exchange(Exchange()),
    lambda e, s: setattr(s, "exchange", Exchange()),
])
def test_running_callbacks_cannot_reenter_or_change_registered_objects(operation):
    """初始化之后配置固定，避免跨批次混入新策略、来源或账户。"""
    exchange, strategy, _, feed = setup()
    with pytest.raises(RuntimeError):
        exchange.run(control=lambda: operation(exchange, strategy))
    assert feed.closed == feed.iterator_closed == 1


@pytest.mark.parametrize("phase", ["prepare", "read", "init", "control", "bar", "sample", "snapshot", "finish"])
def test_execution_failures_preserve_original_exception_and_release_resources(phase):
    """每个执行阶段失败都不能调用成功通知或返回伪完成结果。"""
    failure = RuntimeError(f"failure at {phase}")

    def fail(*args, **kwargs):
        raise failure

    exchange, strategy, broker, feed = setup()
    callback = None
    if phase == "prepare":
        feed.prepare = fail
    elif phase == "read":
        feed.events = fail
    elif phase == "init":
        strategy.on_init = fail
    elif phase == "control":
        callback = fail
    elif phase == "bar":
        strategy.on_bars = fail
    elif phase == "sample":
        strategy._record_broker_history = fail
    elif phase == "snapshot":
        broker.get_total_pnl = fail
    else:
        strategy.on_finish = fail
    with pytest.raises(RuntimeError) as caught:
        exchange.run(control=callback)
    assert caught.value is failure
    assert feed.closed == 1
    assert strategy.finishes == 0
    with pytest.raises(RuntimeError, match="only be run once"):
        exchange.run()


@pytest.mark.parametrize("resource", ["feed", "iterator"])
@pytest.mark.parametrize("business_failure", [False, True])
def test_close_failures_are_visible_but_never_replace_business_exception(resource, business_failure):
    """提前退出时生成器关闭失败必须传播，业务错误存在时则保留原错误。"""
    close_failure = RuntimeError("close failed")
    original = ValueError("strategy failed")

    class BrokenCloseFeed(Feed):
        def events(self):
            try:
                for i, price in enumerate(self.prices):
                    yield Bar(dt(i), "A", "kline", {"close": price})
            finally:
                self.iterator_closed += 1
                if resource == "iterator":
                    raise close_failure

        def close(self):
            super().close()
            if resource == "feed":
                raise close_failure

    exchange, _, _, feed = setup(feed=BrokenCloseFeed((100, 110, 120)))

    def control():
        if business_failure:
            raise original
        return "exit"

    expected = original if business_failure else close_failure
    with pytest.raises(type(expected)) as caught:
        exchange.run(control=control, load_mode="incremental")
    assert caught.value is expected
    assert feed.closed == feed.iterator_closed == 1


def test_long_replay_preserves_old_prefix_and_uses_boundary_equity_for_validation():
    """新增段收益按切点权益计算，不能把旧段的浮盈再算一次。"""
    class SellLater(BuyAndHold):
        def on_bars(self, current_dt, bars):
            super().on_bars(current_dt, bars)
            if current_dt == dt(2):
                self.broker.close_position("A")

    short, _, _, _ = setup((100, 110), strategy_type=SellLater)
    long, _, _, _ = setup((100, 110, 115), strategy_type=SellLater)
    old, extended = short.run(), long.run()
    assert old.get_equity_curve() == extended.get_equity_curve()[:2]
    assert old.get_orders() == extended.get_orders()[:1]
    assert extended.get_equity_curve()[-1][1] - old.get_equity_curve()[-1][1] == 5
    assert extended.get_total_pnl().realized_pnl == 15
