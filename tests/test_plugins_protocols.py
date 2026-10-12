"""验证默认回测独立于插件，以及协议快照的真实隔离。"""

import ast
from dataclasses import fields
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from minbt import Bar, Broker, OrderSnapshot, Strategy, run
from minbt.protocols import BrokerProtocol, DataFeedProtocol, PnlProtocol, ReplayBrokerProtocol, ResultProtocol
from minbt.protocols.broker import BROKER_PROTOCOL_METHODS
from minbt.protocols.result import OrderSnapshot as ProtocolOrderSnapshot


def test_default_backtest_does_not_load_plugins():
    """全新进程内从导入到结果完成均只使用核心，避免其他测试先加载插件掩盖耦合。"""
    code = """
import sys
from minbt import Bar, Broker, Strategy, run

class Feed:
    name = "prepared"
    def events(self):
        yield Bar("2026-01-01", "TEST", "kline", {"close": 100})
        yield Bar("2026-01-02", "TEST", "kline", {"close": 120})

class Hold(Strategy):
    def on_bars(self, dt, bars):
        self.broker.order_target_size("TEST", 1)

result = run(Hold, {"broker": {"initial_cash": 1000}}, feed_factory=lambda _: [Feed()])
assert result.get_equity_curve()[-1][1] == 1020
assert result.get_total_pnl().net_pnl == 20
assert Broker.__module__ == "minbt.broker.broker"
assert not any(name == "minbt.plugins" or name.startswith("minbt.plugins.") for name in sys.modules)
"""
    process = subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=30,
    )
    assert process.returncode == 0, process.stdout + process.stderr


def test_default_implementations_satisfy_protocols():
    assert OrderSnapshot is ProtocolOrderSnapshot
    assert isinstance(Broker(1000), ReplayBrokerProtocol)
    assert isinstance(Feed(), DataFeedProtocol)


def test_protocol_sources_only_import_standard_library_and_protocols():
    """接口声明不得偷偷绑定具体 Broker、读取器、数值或图形 SDK。"""
    directory = Path(__file__).resolve().parents[1] / "minbt" / "protocols"
    standard = {"dataclasses", "datetime", "typing"}
    for path in directory.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                assert all(item.name.split(".")[0] in standard for item in node.names), path
            elif isinstance(node, ast.ImportFrom):
                assert node.level or node.module.split(".")[0] in standard, path


class RecordBroker:
    """用普通记录返回查询数据的交易实现，不继承内置 Broker/Order/Pnl。"""

    def __init__(self):
        backing = Broker(1000)
        self.initial_cash = 1000  # 可选的结果初始资金能力。
        for name in (*BROKER_PROTOCOL_METHODS, "process_market_batch", "get_portfolios"):
            setattr(self, name, getattr(backing, name))
        self.backing = backing  # 仅测试用账本，记录查询转换为用户类型。
        self.order_records = []  # 保存原记录，用来验证结果脱离可变对象。
        self.pnl_record = None  # 查询时创建的可变盈亏记录。

    def get_orders(self):
        self.order_records = [SimpleNamespace(**vars(order)) for order in self.backing.get_orders()]
        return self.order_records

    def get_total_pnl(self):
        native = self.backing.get_total_pnl()
        self.pnl_record = SimpleNamespace(**{field.name: getattr(native, field.name) for field in fields(native)})
        self.pnl_record.net_pnl = native.net_pnl
        return self.pnl_record


class Feed:
    name = "self-prepared"

    def events(self):
        yield Bar("2026-01-01", "ASSET_X", "kline", {"close": 100})
        yield Bar("2026-01-02", "ASSET_X", "kline", {"close": 120})


class Hold(Strategy):
    def on_bars(self, dt, bars):
        self.broker.order_target_size("ASSET_X", 1)


def test_plain_records_freeze_into_standard_result_without_inheritance():
    """活记录和返回容器改变之后，结果权益、订单和盈亏仍与真实交易一致。"""
    broker = RecordBroker()
    result = run(Hold, {"broker": {}}, feed_factory=lambda _: [Feed()], broker_factory=lambda _: broker)
    assert isinstance(broker, BrokerProtocol)
    assert isinstance(result, ResultProtocol)
    assert result.get_equity_curve()[-1][1] == 1020
    assert result.get_total_pnl().net_pnl == 20
    assert isinstance(result.get_total_pnl(), PnlProtocol)
    broker.order_records[0].qty = 900
    broker.pnl_record.unrealized_pnl = 900
    orders = result.get_orders()
    orders.clear()
    assert result.get_orders()[0].qty == 1
    assert result.get_total_pnl().unrealized_pnl == 20


@pytest.mark.parametrize("invalid", ["order_fields", "pnl_fields", "pnl_formula", "pnl_nonfinite"])
def test_bad_record_contracts_do_not_produce_fake_results(invalid):
    """缺少字段或与四项盈亏矛盾时失败，不能伪造标准结果。"""
    broker = RecordBroker()
    if invalid == "order_fields":
        broker.get_orders = lambda: [SimpleNamespace(id="missing")]
    elif invalid == "pnl_fields":
        broker.get_total_pnl = lambda: SimpleNamespace(net_pnl=20)
    else:
        query = broker.get_total_pnl

        def incorrect():
            record = query()
            if invalid == "pnl_nonfinite":
                record.unrealized_pnl = record.net_pnl = float("nan")
            else:
                record.net_pnl = 999
            return record

        broker.get_total_pnl = incorrect
    with pytest.raises((TypeError, ValueError), match="standard"):
        run(Hold, {"broker": {}}, feed_factory=lambda _: [Feed()], broker_factory=lambda _: broker)
