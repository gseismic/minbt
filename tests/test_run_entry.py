"""验证配置入口与手工装配等价，以及装配、运行和退出的真实资源边界。"""

from copy import deepcopy
import json
from types import MappingProxyType

import pytest

from minbt import Bar, Broker, Exchange, Strategy, run
from minbt.protocols import ResultProtocol


class PreparedFeed:
    """用户自备价格与关闭计数，用来观察运行而不访问任何数据服务。"""

    name = "prepared"

    def __init__(self, prices=(100, 110, 120)):
        self.prices = prices  # 调用方准备的确定性价格。
        self.closed = 0  # 记录资源是否被重复释放。

    def events(self):
        for index, price in enumerate(self.prices, 1):
            yield Bar(f"2026-01-{index:02d}", "ASSET_X", "kline", {"close": price})

    def close(self):
        self.closed += 1


class Hold(Strategy):
    """固定买入一单位，给出可手工核对的权益和订单基线。"""

    def on_bars(self, dt, bars):
        self.broker.order_target_size("ASSET_X", self.params.get("qty", 1))


class ClosingBroker(Broker):
    """模拟带资源的自定义 Broker，观察收尾且不改变正常交易行为。"""

    def __init__(self, initial_cash=1000):
        super().__init__(initial_cash)
        self.closed = 0  # 新入口应释放的资源次数。

    def close(self):
        self.closed += 1


def config():
    return {
        "strategy": {"id": "hold", "params": {"qty": 1}},
        "data": {"path": "user-owned", "custom": {"flag": True}},
        "broker": {"initial_cash": 1000},
    }


def test_json_and_mapping_match_manual_without_changing_input(tmp_path):
    """两种配置来源得到同一真实结果，工厂可改自己的副本而不污染用户参数。"""
    options = config()
    original = deepcopy(options)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(options))
    feeds = []

    def factory(data):
        assert data == original["data"]
        data["custom"]["flag"] = False
        feed = PreparedFeed()
        feeds.append(feed)
        return [feed]

    mapping_result = run(Hold, MappingProxyType(options), feed_factory=factory)
    file_result = run(Hold, path, feed_factory=factory)
    broker = Broker(1000)
    manual = Exchange()
    manual.add_feed(PreparedFeed())
    strategy = Hold("hold", broker=broker, params={"qty": 1})
    manual.add_strategy(strategy)
    expected = manual.run()

    for result in (mapping_result, file_result):
        assert result.get_equity_curve() == expected.get_equity_curve()
        assert result.get_orders() == expected.get_orders()
        assert result.get_position_curve("ASSET_X") == expected.get_position_curve("ASSET_X")
        assert result.get_total_pnl() == expected.get_total_pnl()
        assert result.meta == expected.meta
        assert result.get_equity_curve()[-1][1] == 1020
        assert isinstance(result, ResultProtocol)
    assert options == original
    assert feeds[0] is not feeds[1]
    assert [feed.closed for feed in feeds] == [1, 1]


def test_factory_broker_and_default_id_create_new_experiments():
    """每次工厂收到自己的参数并创建新账户，已关闭的账户不污染结果。"""
    options = config()
    options.pop("strategy")
    brokers = []

    def factory(parameters):
        broker = ClosingBroker(**parameters)
        brokers.append(broker)
        return broker

    first = run(Hold, options, feed_factory=lambda _: [PreparedFeed()], broker_factory=factory)
    second = run(Hold, options, feed_factory=lambda _: [PreparedFeed((100, 90))], broker_factory=factory)
    assert first.meta["strategy_ids"] == ("Hold",)
    assert first.get_total_pnl().net_pnl == 20
    assert second.get_total_pnl().net_pnl == -10
    assert brokers[0] is not brokers[1]
    assert [broker.closed for broker in brokers] == [1, 1]


def test_falsey_callable_factory_is_not_replaced_by_default():
    """显式可调用对象的真值不能决定是否忽略用户提供的工厂。"""
    broker = ClosingBroker()

    class Factory:
        def __bool__(self):
            return False

        def __call__(self, parameters):
            return broker

    result = run(Hold, config(), feed_factory=lambda _: [PreparedFeed()], broker_factory=Factory())
    assert broker.closed == 1
    assert result.get_total_pnl().net_pnl == 20


@pytest.mark.parametrize("load_mode", ["auto", "preload", "incremental"])
def test_window_pause_and_exit_keep_original_control_semantics(load_mode):
    """暂停仍计价，退出保留最后完整批次；窗口和三种读取模式一致。"""
    options = config()
    options["run"] = {"start": "2026-01-02", "end": "2026-01-05", "load_mode": load_mode}
    feed = PreparedFeed((100, 110, 120, 900))
    feed.ordered = feed.supports_incremental = True
    actions = iter(("continue", "pause", "exit"))
    result = run(Hold, options, feed_factory=lambda _: [feed], control=lambda: next(actions))
    assert result.meta["status"] == "exited"
    assert result.meta["step_count"] == 2
    assert [value for _, value in result.get_equity_curve()] == [1000, 1010]
    assert len(result.get_orders()) == 1
    assert result.get_position_sizes() == {"ASSET_X": 1}
    assert feed.closed == 1


def test_signal_configuration_has_no_fake_account():
    """broker=null 不调用账户工厂，纯信号结果保持没有账户的明确异常。"""
    options = config()
    options["broker"] = None
    calls = []
    result = run(
        Strategy, options, feed_factory=lambda _: [PreparedFeed()],
        broker_factory=lambda _: calls.append(True),
    )
    assert calls == []
    assert result.meta["step_count"] == 3
    with pytest.raises(ValueError, match="no Broker"):
        result.get_equity_curve()


@pytest.mark.parametrize("stage", ["iteration", "registration", "constructor", "window", "prepare", "callback"])
def test_setup_and_execution_failures_release_all_resources(stage):
    """工厂部分成功、预检及启动后失败都释放资源，不能由 Exchange 和入口重复关闭。"""
    feed = PreparedFeed()
    broker = ClosingBroker()
    options = config()
    strategy_class = Hold

    def factory(_):
        yield feed
        if stage == "iteration":
            raise RuntimeError("factory iteration")
        if stage == "registration":
            yield feed

    if stage == "constructor":
        class Broken(Strategy):
            def __init__(self, **kwargs):
                raise RuntimeError("constructor")
        strategy_class = Broken
    elif stage == "window":
        options["run"] = {"start": "2026-02-01", "end": "2026-01-01"}
    elif stage == "prepare":
        def fail():
            raise RuntimeError("prepare")
        feed.prepare = fail
    elif stage == "callback":
        class Broken(Hold):
            def on_bars(self, dt, bars):
                raise RuntimeError("callback")
        strategy_class = Broken

    with pytest.raises((RuntimeError, ValueError)):
        run(strategy_class, options, feed_factory=factory, broker_factory=lambda _: broker)
    assert feed.closed == 1
    assert broker.closed == 1


def test_cleanup_errors_do_not_hide_factory_error():
    """关闭失败也尝试释放其余资源，原工厂错误仍然传播。"""
    broker = ClosingBroker()
    feed = PreparedFeed()

    def close():
        feed.closed += 1
        raise OSError("close feed")

    feed.close = close

    def factory(_):
        yield feed
        raise RuntimeError("factory failed")

    with pytest.raises(RuntimeError, match="factory failed"):
        run(Hold, config(), feed_factory=factory, broker_factory=lambda _: broker)
    assert broker.closed == feed.closed == 1


def test_close_property_failure_still_releases_other_resources():
    """自定义 close 属性访问失败属于资源错误，不能跳过其他对象的释放。"""
    broker = ClosingBroker()

    class BrokenFeed:
        name = "broken"

        def events(self):
            return iter(())

        @property
        def close(self):
            raise OSError("close lookup")

    with pytest.raises(ValueError, match="start must be earlier"):
        run(
            Hold, {**config(), "run": {"start": "2026-02-01", "end": "2026-01-01"}},
            feed_factory=lambda _: [BrokenFeed()], broker_factory=lambda _: broker,
        )
    assert broker.closed == 1


def test_broker_close_failure_is_not_a_completed_result():
    """正常运行后的资源失败仍抛异常，不返回伪成功。"""
    broker = ClosingBroker()

    def close():
        broker.closed += 1
        raise OSError("broker close")

    broker.close = close
    with pytest.raises(OSError, match="broker close"):
        run(Hold, config(), feed_factory=lambda _: [PreparedFeed()], broker_factory=lambda _: broker)
    assert broker.closed == 1


@pytest.mark.parametrize("update", [
    {"unknown": 1}, {"strategy": []}, {"data": []}, {"broker": []}, {"run": []},
    {"strategy": {"id": ""}}, {"strategy": {"params": []}},
    {"strategy": {"unknown": 1}}, {"run": {"control": "exit"}},
])
def test_invalid_config_fails_before_factories(update):
    """拼写和形状错误不触发用户读取或账户创建。"""
    calls = []
    with pytest.raises((ValueError, TypeError)):
        run(Hold, {**config(), **update}, feed_factory=lambda _: calls.append(True))
    assert calls == []


def test_missing_default_account_parameters_fail_before_reading():
    """缺少 initial_cash 不偷偷创建无资金账户或纯信号实验。"""
    with pytest.raises(TypeError, match="initial_cash"):
        run(Hold, {"data": {}}, feed_factory=lambda _: pytest.fail("must not read"))


def test_invalid_broker_factory_output_is_closed():
    """错误工厂产品仍是已转交资源，需要在契约校验失败后释放。"""
    class InvalidBroker:
        closed = False

        def close(self):
            self.closed = True

    broker = InvalidBroker()
    with pytest.raises(TypeError, match="ReplayBrokerProtocol"):
        run(Hold, config(), feed_factory=lambda _: [], broker_factory=lambda _: broker)
    assert broker.closed


def test_noncallable_replay_method_is_rejected_before_data_creation():
    """只有同名属性的伪回放账户不应等到启动后才失败，已创建账户仍会释放。"""
    broker = ClosingBroker()
    broker.process_market_batch = 1
    with pytest.raises(TypeError, match="ReplayBrokerProtocol"):
        run(
            Hold, config(), broker_factory=lambda _: broker,
            feed_factory=lambda _: pytest.fail("must reject before reading"),
        )
    assert broker.closed == 1


def test_external_engine_owns_factories_and_returns_protocol_result():
    """核心只委托一次，不重复创建账户/读数据，也不另建结果缓存。"""
    calls = []

    class ForeignResult:
        def __init__(self, native):
            self.meta = native.meta
            for name in (
                "get_initial_cash", "get_equity_curve", "get_position_curve", "get_orders",
                "get_total_pnl", "get_position_sizes",
            ):
                setattr(self, name, getattr(native, name))

    class Engine:
        def run(self, strategy_class, parameters, **kwargs):
            calls.append(parameters)
            self.result = ForeignResult(run(strategy_class, parameters, **kwargs))
            return self.result

    reads = []
    engine = Engine()
    result = run(
        Hold, config(), engine=engine,
        feed_factory=lambda _: (reads.append(True) or [PreparedFeed()]),
    )
    assert result is engine.result
    assert result.get_total_pnl().net_pnl == 20
    assert len(calls) == len(reads) == 1
    assert isinstance(result, ResultProtocol)


def test_invalid_engine_result_fails_without_default_data_loading():
    class Engine:
        def run(self, *args, **kwargs):
            return object()

    with pytest.raises(TypeError, match="ResultProtocol"):
        run(Hold, config(), engine=Engine(), feed_factory=lambda _: pytest.fail("not delegated"))
