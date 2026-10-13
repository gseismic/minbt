"""第九、十轮回归：验证成交原子性、全仓减仓以及行情和交易时间边界。"""

import copy
import csv
import importlib.util
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from minbt import Bar, Broker, Exchange, Market, Strategy
from minbt.broker.portfolio import Portfolio
from minbt.broker.struct import Cash, Position
from minbt.data.model import normalize_datetime
from minbt.data.replay import BatchItem, TimeBatch
from minbt.plugins.storage import CsvBarFeed, IosqlBarFeed
from minbt.plugins.storage.bar_feed import _BarRowFeed


def _batch(prices, dt="2026-01-02"):
    dt = normalize_datetime(dt)
    return TimeBatch(dt, tuple(
        BatchItem("prices", 0, 0, i, Bar(dt, symbol, "kline", {"close": price}))
        for i, (symbol, price) in enumerate(prices.items())
    ))


def _state(broker):
    """同时核对价格、时钟、资金、持仓和账本，不能只检查现金没变。"""
    return (
        broker.last_prices.copy(), broker.last_price_dates.copy(), broker._last_market_dt,
        broker.get_cash(), broker.get_total_equity(), broker.get_position_sizes(),
        broker.get_total_pnl(), broker.get_pnl_records(),
        copy.deepcopy([asdict(order) for order in broker.get_orders()]),
    )


@pytest.mark.parametrize("price", [29, 2.9, 0.29, 1e-8])
def test_full_weight_target_accepts_only_float_cash_tail(price):
    """R9-03：正常满仓数量乘价格的尾差不能造成随机拒单。"""
    broker = Broker(1000)
    order = broker.order_target_percent("A", 1, price=price)
    assert order.status == "filled"
    assert broker.get_cash() == 0
    assert broker.get_position_size("A") == pytest.approx(1000 / price)
    assert broker.get_total_equity() == pytest.approx(1000)
    assert broker.get_total_pnl().net_pnl == pytest.approx(0)


def test_real_cash_shortfall_is_still_rejected():
    """金额超支明显大于浮点间距时保持拒单，不能用宽泛容差借钱开仓。"""
    broker = Broker(1000)
    order = broker.submit_market_order("A", 1000.001 / 29, price=29)
    assert order.status == "rejected"
    assert broker.get_cash() == 1000
    assert broker.get_position("A") is None
    assert broker.get_pnl_records() == []


@pytest.mark.parametrize("locked", [0, 200])
def test_cash_precheck_and_commit_share_zero_balance_rule(locked):
    """现金预检与提交必须一致，尾差归零也不能改变已锁定金额。"""
    cash = Cash(1000 + locked, 1000)
    assert cash.can_change_cash(-1000.0000000000001)
    cash.change_cash(-1000.0000000000001)
    assert (cash.free_cash, cash.total_cash, cash.locked_cash) == (0, locked, locked)
    before = repr(cash)
    assert not cash.can_change_cash(-0.001)
    with pytest.raises(ValueError, match="negative"):
        cash.change_cash(-0.001)
    assert repr(cash) == before


@pytest.mark.parametrize("method,args", [
    ("submit_market_order", (1e308,)),
    ("submit_limit_order", (1e308, 100)),
    ("order_target_size", (1e308,)),
    ("order_target_value", (1e308,)),
    ("order_target_percent", (1e308,)),
])
def test_overflow_rejects_before_price_clock_or_order_side_effects(method, args):
    """R9-04：极大有限请求不能留下新报价、部分仓位或 pending 市价单。"""
    broker = Broker(1000)
    old = broker.submit_market_order("OLD", 1, price=100, price_dt="2026-01-01", stop_loss_price=90)
    before = _state(broker)
    options = {"price_dt": "2026-01-02"}
    if method != "submit_limit_order":
        options["price"] = 100 if method != "order_target_value" else 1e-308
    with pytest.raises(ValueError, match="finite"):
        getattr(broker, method)("A", *args, **options)
    assert _state(broker) == before
    assert broker.get_exit(old.id).active


def test_standalone_portfolio_overflow_does_not_change_live_position():
    """独立分仓也在副本上拒绝派生值溢出，不能只修复 Broker 转发入口。"""
    portfolio = Portfolio(1000, 0)
    assert portfolio.submit_order("A", 1, 100, price_dt=normalize_datetime("2026-01-01"))
    position = portfolio.get_position("A")
    before = copy.deepcopy(position.__dict__)
    records = portfolio.get_pnl_records()
    with pytest.raises(ValueError, match="finite"):
        portfolio.submit_order("A", 1e300, 1e10)
    assert portfolio.get_position("A") is position
    assert position.__dict__ == before
    assert portfolio.get_cash() == 900
    assert portfolio.get_pnl_records() == records


def test_target_percent_checks_projected_equity_before_publishing_quote():
    """当前权益乘比例有限、上涨后的权益乘比例溢出时，也必须保持行情和时钟。"""
    broker = Broker(1000)
    order = broker.submit_market_order("A", 1, price=100, price_dt="2026-01-01", stop_loss_price=90)
    before = _state(broker)
    with pytest.raises(ValueError, match="target_value must be finite"):
        broker.order_target_percent("A", 1e305, price=1000, price_dt="2026-01-02")
    assert _state(broker) == before
    assert broker.get_exit(order.id).active


def test_accumulated_position_size_overflow_is_atomic():
    """单笔名义金额有限仍可能使总数量溢出，必须验证候选持仓。"""
    broker = Broker(1.6e308, leverage=10)
    assert broker.submit_market_order("A", 1e308, price=1).status == "filled"
    position = broker.get_position("A")
    before = _state(broker)
    with pytest.raises(ValueError, match="finite"):
        broker.submit_market_order("A", 1e308, price=1)
    assert _state(broker) == before
    assert broker.get_position("A") is position


def test_pending_order_becomes_rejected_if_later_position_would_overflow():
    """提交后其他成交改变了数量边界，挂单触发失败必须明确终结且不部分成交。"""
    broker = Broker(1.6e308, leverage=10)
    pending = broker.submit_limit_order("A", 1e308, 1)
    assert pending.status == "pending"
    assert broker.submit_market_order("A", 1e308, price=1).status == "filled"
    records = broker.get_pnl_records()
    broker.process_market_batch(_batch({"A": 1}))
    assert pending.status == "rejected" and pending.filled_qty == 0
    assert "finite" in pending.reason
    assert broker.get_position_size("A") == 1e308
    assert broker.get_cash() == 1.5e308
    assert broker.get_pnl_records() == records


@pytest.mark.parametrize("entry", ["on_new_price", "submit_market_order", "process_market_batch"])
def test_quote_overflow_in_other_portfolio_is_rejected_before_any_update(entry):
    """显式报价影响所有分仓，其他分仓的溢出也不能留下新报价或新时钟。"""
    broker = Broker(1000, leverage=10)
    broker.add_portfolio("beta", 500)
    broker.submit_market_order("A", 10, price=100, price_dt="2026-01-01", portfolio="beta")
    position = broker.get_position("A", portfolio="beta")
    before = _state(broker)
    beta_state = copy.deepcopy(position.__dict__)
    with pytest.raises(ValueError, match="finite"):
        if entry == "process_market_batch":
            broker.process_market_batch(_batch({"A": 1e308}))
        elif entry == "on_new_price":
            broker.on_new_price("A", 1e308, "2026-01-02")
        else:
            broker.submit_market_order("A", 1e-308, price=1e308, price_dt="2026-01-02")
    assert _state(broker) == before
    assert position.__dict__ == beta_state


def test_position_and_cash_derived_overflow_preserve_their_state():
    """基础数值对象也先检查候选值，不能先写成本或余额再抛异常。"""
    position = Position("A")
    before = copy.deepcopy(position.__dict__)
    with pytest.raises(ValueError, match="finite"):
        position.commit_open_new(100, 1e308, 1)
    assert position.__dict__ == before
    cash = Cash(1e308, 1e308)
    with pytest.raises(ValueError, match="finite"):
        cash.add_cash(1e308)
    assert cash.free_cash == cash.total_cash == 1e308


@pytest.mark.parametrize("sequence", [("A", "B"), ("B", "A")])
@pytest.mark.parametrize("fee_rate", [0, 0.001])
@pytest.mark.parametrize("portfolio", ["main", "sub"])
def test_cross_atomic_close_is_independent_of_position_order(sequence, fee_rate, portfolio):
    """R9-02：亏损腿释放负现金时，两种建仓顺序都应完整结算并正确归档。"""
    allocated = 1000 + 10000 * fee_rate
    broker = Broker(allocated + (100 if portfolio == "sub" else 0), fee_rate=fee_rate, leverage=10)
    if portfolio == "sub":
        broker.add_portfolio(portfolio, allocated)
    for symbol in sequence:
        assert broker.submit_market_order(symbol, 50, price=100, portfolio=portfolio).status == "filled"
    broker.process_market_batch(_batch({"A": 89, "B": 94}))
    orders = broker.close_portfolio(portfolio)
    assert [order.status for order in orders] == ["filled", "filled"]
    assert broker.get_position_sizes() == {}
    expected = 150 - 9150 * fee_rate + (100 if portfolio == "sub" else 0)
    assert broker.get_cash() == pytest.approx(expected)
    assert broker.get_total_equity() - broker.initial_cash == pytest.approx(broker.get_total_pnl().net_pnl)
    assert broker.get_portfolios() == ["main"]
    assert broker.get_pnl(portfolio=portfolio).realized_pnl == -850


@pytest.mark.parametrize("method,target", [("close_position", None), ("order_target_size", 5), ("submit_market_order", -5)])
def test_cross_reduce_only_uses_equity_and_can_repay_cash_debt(method, target):
    """R10-01：有效减仓可形成有权益支撑的欠款，但欠款不得资助加仓或反手。"""
    broker = Broker(200, leverage=10)
    for symbol in ("A", "B"):
        broker.submit_market_order(symbol, 10, price=100)
    broker.process_market_batch(_batch({"A": 85, "B": 112}))
    position = broker.get_position("A")
    args = () if target is None else (target,)
    order = getattr(broker, method)("A", *args)
    assert order.status == "filled"
    assert broker.get_position("A") is position
    assert broker.get_cash() == (-50 if target is None else -25)
    assert broker.get_total_equity() == 170
    assert broker.get_total_pnl().net_pnl == -30
    records = broker.get_pnl_records()
    for symbol, qty in (("A", 1), ("B", 1), ("C", 1), ("B", -11)):
        rejected = broker.submit_market_order(symbol, qty, price=100 if symbol == "C" else None)
        assert rejected.status == "rejected"
    with pytest.raises(ValueError, match="free cash"):
        broker.add_portfolio("unfunded", 1)
    assert broker.get_pnl_records() == records
    assert broker.close_position("B").status == "filled"
    if broker.get_position_size("A"):
        assert broker.close_position("A").status == "filled"
    assert broker.get_cash() == broker.get_total_equity() == 170


@pytest.mark.parametrize("load_mode", ["preload", "incremental"])
def test_cross_stop_loss_closes_losing_leg_in_real_replay(load_mode):
    """R10-01：止损不因现金全被保证金占用而失效，后续反弹也不能恢复旧仓位。"""
    class Protected(Strategy):
        def on_bars(self, dt, bars):
            if dt == normalize_datetime("2026-01-01"):
                self.broker.submit_market_order("A", 10, stop_loss_price=95)
                self.broker.submit_market_order("B", 10)

    broker = Broker(200, leverage=10)
    exchange = Exchange()
    exchange.set_bars([
        {"dt": day, "symbol": symbol, "close": price}
        for day, prices in (("2026-01-01", {"A": 100, "B": 100}),
                            ("2026-01-02", {"A": 85, "B": 112}),
                            ("2026-01-03", {"A": 96, "B": 112}))
        for symbol, price in prices.items()
    ])
    exchange.add_strategy(Protected("protected", broker))
    result = exchange.run(load_mode=load_mode)
    assert broker.get_position_sizes() == {"B": 10}
    assert broker.get_cash() == -50
    assert result.get_total_pnl().net_pnl == -30
    assert result.get_orders()[-1].status == "filled"
    assert not broker.get_exit("order-1").active


@pytest.mark.parametrize("price,expected,reason", [(96, 10, "liquidation"), (90, 0, "bankruptcy")])
def test_cross_cash_debt_does_not_bypass_future_risk(price, expected, reason):
    """减仓后的欠款仍计入强平和穿仓，不能通过负现金隐藏账户损失。"""
    broker = Broker(200, leverage=10)
    for symbol in ("A", "B"):
        broker.submit_market_order(symbol, 10, price=100)
    broker.process_market_batch(_batch({"A": 85, "B": 112}))
    assert broker.close_position("A").status == "filled"
    broker.process_market_batch(_batch({"B": price}, "2026-01-03"))
    assert broker.get_position_sizes() == {}
    assert broker.get_cash() == broker.get_total_equity() == expected
    assert broker.get_total_pnl().net_pnl == expected - 200
    assert any(record.reason == reason for record in broker.get_pnl_records())


@pytest.mark.parametrize("sequence", [("A", "B"), ("B", "A")])
def test_close_plan_with_unpayable_fees_preserves_live_account(sequence):
    """全平手续费超过账户权益时仍整体拒绝，预检不得修改真实持仓或记账。"""
    broker = Broker(400, fee_rate=0.1, leverage=10)
    for symbol in sequence:
        broker.submit_market_order(symbol, 10, price=100)
    broker.process_market_batch(_batch({"A": 85, "B": 112}))
    before = (broker.get_cash(), broker.get_position_sizes(), broker.get_total_pnl(), broker.get_pnl_records())
    assert broker.close_portfolio("main")[0].status == "rejected"
    assert (broker.get_cash(), broker.get_position_sizes(), broker.get_total_pnl(), broker.get_pnl_records()) == before


def test_cross_reduce_only_still_respects_t_plus_one():
    """减仓结算例外仅影响资金，不允许绕过市场的可平数量限制。"""
    broker = Broker(200, leverage=10, market=Market(t_plus=1))
    for symbol in ("A", "B"):
        broker.submit_market_order(symbol, 10, price=100, price_dt="2026-01-01")
    broker.process_market_batch(_batch({"A": 85, "B": 112}, "2026-01-01T12:00:00Z"))
    assert broker.close_position("A").status == "rejected"
    broker.process_market_batch(_batch({"OTHER": 1}))
    assert broker.close_position("A").status == "filled"
    assert broker.get_cash() == -50


def test_closed_portfolio_cash_can_partially_repay_main_debt():
    """其他分仓的正现金可以分次归还 main，不能在已删分仓后因余额仍负而抛错。"""
    broker = Broker(1000, leverage=10)
    broker.add_portfolio("sub", 100)
    for symbol in ("A", "B"):
        broker.submit_market_order(symbol, 45, price=100)
    broker.process_market_batch(_batch({"A": 85, "B": 112}))
    assert broker.close_position("A").status == "filled"
    assert broker.get_cash() == -225
    before = broker.get_total_equity(), broker.get_total_pnl()
    assert broker.close_portfolio("sub")[0].status == "skipped"
    assert broker.get_portfolios() == ["main"]
    assert broker.get_cash() == -125
    assert (broker.get_total_equity(), broker.get_total_pnl()) == before


@pytest.mark.parametrize("has_position", [False, True])
def test_return_cash_overflow_preserves_portfolio_and_pending_orders(has_position):
    """接收分仓余额溢出时，不能先成交、取消挂单或删除分仓。"""
    broker = Broker(1.6e308, leverage=10)
    broker.add_portfolio("sub", 6e307)
    for symbol in ("P", "L"):
        broker.submit_market_order(symbol, 5e307, price=1)
    broker.process_market_batch(_batch({"P": 1.8, "L": 0.4}))
    assert broker.close_position("P").status == "filled"
    if has_position:
        broker.submit_market_order("C", 1e307, price=1, portfolio="sub")
    pending = broker.submit_limit_order("C", 1, 0.5, portfolio="sub")
    assert pending.status == "pending"
    before = _state(broker)
    sub_before = broker.get_position_sizes(portfolio="sub"), broker.get_cash(portfolio="sub")
    with pytest.raises(ValueError, match="finite"):
        broker.close_portfolio("sub")
    assert _state(broker) == before
    assert broker.get_position_sizes(portfolio="sub") == sub_before[0]
    assert broker.get_cash(portfolio="sub") == sub_before[1]
    assert pending.status == "pending"


@pytest.mark.parametrize("load_mode", ["preload", "incremental"])
def test_news_exit_keeps_other_portfolios_quote_time(load_mode):
    """R9-07：News 触发 alpha 退出只推进成交时间，不伪造 beta 的新行情。"""
    class NewsExit(Strategy):
        def on_bars(self, dt, bars):
            order = self.broker.submit_market_order("A", 1, portfolio="alpha")
            self.broker.submit_market_order("A", 1, portfolio="beta")
            self.broker.add_exit(order.id, condition=lambda ctx: ctx.dt == normalize_datetime("2026-01-02"))

    broker = Broker(1000)
    broker.add_portfolio("alpha", 200)
    broker.add_portfolio("beta", 200)
    exchange = Exchange()
    exchange.set_bars([{"dt": "2026-01-01", "symbol": "A", "close": 100}])
    exchange.set_news([{"dt": "2026-01-02", "text": "other news"}])
    exchange.add_strategy(NewsExit("news", broker))
    result = exchange.run(load_mode=load_mode)
    quote_dt = normalize_datetime("2026-01-01")
    trade_dt = normalize_datetime("2026-01-02")
    assert broker.get_last_price("A", return_dt=True) == (100, quote_dt)
    assert broker.get_position("A", portfolio="beta")._last_dt == quote_dt
    assert broker.portfolios["beta"].last_prices_dt["A"] == quote_dt
    assert result.get_orders()[-1].updated_dt == trade_dt
    assert broker.get_pnl_records()[-1].dt == trade_dt


def test_manual_exit_check_uses_current_trade_time_without_republishing_quote():
    """手动检查退出也使用传入的交易时间，保留原行情时间。"""
    broker = Broker(1000)
    order = broker.submit_market_order("A", 1, price=100, price_dt="2026-01-01")
    broker.add_exit(order.id, condition=lambda ctx: True)
    broker.check_exit_rules(dt="2026-01-02")
    assert broker.get_last_price("A", return_dt=True)[1] == normalize_datetime("2026-01-01")
    assert broker.get_orders()[-1].updated_dt == normalize_datetime("2026-01-02")


@pytest.mark.parametrize("close_portfolio", [False, True])
def test_cancel_records_actual_state_change_time(close_portfolio):
    """R9-08：用户撤单与关闭分仓撤单都记录当前时钟，原订单创建时间不变。"""
    broker = Broker(1000)
    broker.add_portfolio("sub", 200)
    broker.on_new_price("A", 100, "2026-01-01")
    pending = broker.submit_limit_order("A", 1, 90, portfolio="sub")
    broker.process_market_batch(_batch({"OTHER": 1}))
    if close_portfolio:
        broker.close_portfolio("sub")
    else:
        action = broker.cancel_order(pending.id)
        assert action.id != pending.id and action.source == "cancel_order"
        assert action.created_dt == action.updated_dt == normalize_datetime("2026-01-02")
    assert pending.status == "canceled"
    assert pending.created_dt == normalize_datetime("2026-01-01")
    assert pending.updated_dt == normalize_datetime("2026-01-02")


@pytest.mark.parametrize("method", ["close_position", "close_all_positions"])
def test_standalone_close_keeps_existing_quote_time(method):
    """R10-11：沿用报价平仓不能把报价时间清为 None。"""
    portfolio = Portfolio(1000, 0)
    quote_dt = normalize_datetime("2026-01-01")
    portfolio.submit_order("A", 1, 100, price_dt=quote_dt)
    getattr(portfolio, method)(*("A",) if method == "close_position" else ())
    assert portfolio.last_prices_dt["A"] == quote_dt
    assert portfolio.get_position("A")._last_dt == quote_dt
    assert portfolio.get_position_sizes() == {}


@pytest.mark.parametrize("name", [None, 123, True, [], "", "  ", "\t\n"])
def test_invalid_portfolio_name_is_rejected_before_transfer(name):
    """R10-12：非法名称不得划走现金或创建无法通过公开接口访问的分仓。"""
    broker = Broker(1000)
    with pytest.raises((TypeError, ValueError), match="portfolio name"):
        broker.add_portfolio(name, 100)
    assert broker.get_portfolios() == ["main"]
    assert broker.get_cash() == broker.get_total_equity() == 1000


@pytest.mark.parametrize("value", [1000, 60000, -1000, "1000"])
def test_explicit_dt_ms_never_uses_magnitude_inference(value):
    """R9-09：已知毫秒单位的早期、负值和文本时间戳必须按毫秒解释。"""
    feed = _BarRowFeed()
    feed.name = "row"
    event = feed._normalize_row({"dt_ms": value, "symbol": "A", "kind": "price", "data": {"value": 1}})
    assert event.dt == datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=int(value))


def test_iosql_millisecond_contract_and_query_window(monkeypatch):
    """用受控 Database 驱动真实 Feed，验证存储单位、查询边界和资源关闭。"""
    instances = []

    class Query:
        def iter_rows(self, batch_size):
            yield {"dt": 1000, "symbol": "A", "kind": "price", "data": '{"value":1}'}

    class Table:
        def query(self, **kwargs):
            assert kwargs["start"] == 1000 and kwargs["end"] == 1999
            return Query()

    class Database:
        def __init__(self, uri):
            self.closed = False
            instances.append(self)

        def table_names(self):
            return ["bars"]

        def table(self, name):
            return Table()

        def close(self):
            self.closed = True

    monkeypatch.setitem(sys.modules, "iosql", SimpleNamespace(Database=Database))
    feed = IosqlBarFeed("sqlite:///unused", start="1970-01-01T00:00:01Z", end="1970-01-01T00:00:02Z")
    events = list(feed.events())
    assert [event.dt for event in events] == [datetime(1970, 1, 1, 0, 0, 1, tzinfo=timezone.utc)]
    assert instances[0].closed


def test_generic_csv_dt_still_allows_seconds_and_iso_text(tmp_path):
    """毫秒修复不能改变普通 CSV dt 自动推断与 ISO 文本的现有契约。"""
    path = tmp_path / "bars.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["dt", "symbol", "kind", "data"])
        writer.writerow([1, "A", "price", '{"value":1}'])
        writer.writerow(["1970-01-01T00:00:02Z", "A", "price", '{"value":2}'])
    assert [event.dt.second for event in CsvBarFeed(path).events()] == [1, 2]


def test_moving_average_example_publishes_close_at_completion(monkeypatch):
    """R9-05：运行实际示例，核对回调时间与 CSV 的完成时间并保留开盘字段。"""
    path = Path(__file__).resolve().parents[1] / "examples" / "02_moving_average.py"
    spec = importlib.util.spec_from_file_location("example_sma_time", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observed = []
    original = module.SingleSymbolSmaStrategy.on_bars
    with module.DATA_PATH.open(newline="", encoding="utf-8") as handle:
        expected = {int(row["open_time"]): normalize_datetime(int(row["close_time"]), unit="ms")
                    for row in csv.DictReader(handle)}

    def probe(self, dt, bars):
        row = bars[module.SYMBOL]
        observed.append((dt, row["open_time"]))
        original(self, dt, bars)

    monkeypatch.setattr(module.SingleSymbolSmaStrategy, "on_bars", probe)
    strategy, broker = module.run_strategy()
    assert observed
    for dt, opened in observed:
        assert dt == expected[opened]
        assert normalize_datetime(opened, unit="ms") < dt
    assert broker.get_total_equity() - broker.initial_cash == pytest.approx(broker.get_total_pnl().net_pnl)
    assert strategy.trade_count > 0
