from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from minbt import Bar, Broker, Pnl, PnlRecord
from minbt.broker.portfolio import Portfolio
from minbt.data.replay import BatchItem, TimeBatch


def assert_pnl(pnl, *, realized=0.0, unrealized=0.0, fees=0.0, adjustment=0.0):
    """用独立预期金额验证每个口径及其净盈亏关系。"""
    assert isinstance(pnl, Pnl)
    assert pnl.realized_pnl == pytest.approx(realized)
    assert pnl.unrealized_pnl == pytest.approx(unrealized)
    assert pnl.fees == pytest.approx(fees)
    assert pnl.settlement_adjustment == pytest.approx(adjustment)
    assert pnl.net_pnl == pytest.approx(realized + unrealized - fees + adjustment)


def assert_account_reconciles(broker):
    """实际权益差、汇总与逐条记账必须对齐，避免只验证一套统计的自洽性。"""
    pnl = broker.get_total_pnl()
    records = broker.get_pnl_records()
    assert pnl.net_pnl == pytest.approx(broker.get_total_equity() - broker.initial_cash)
    assert pnl.realized_pnl == pytest.approx(sum(record.realized_pnl for record in records))
    assert pnl.fees == pytest.approx(sum(record.fees for record in records))
    assert pnl.settlement_adjustment == pytest.approx(sum(record.settlement_adjustment for record in records))
    assert pnl.net_pnl == pytest.approx(sum(record.net_pnl for record in records) + pnl.unrealized_pnl)


def update_prices(broker, prices, *, batch):
    """通过 Broker 两种真实行情入口覆盖单价和同时间批量风险结算。"""
    dt = datetime(2026, 1, 2, tzinfo=timezone.utc)
    if batch:
        items = tuple(
            BatchItem("prices", 0, 0, index, Bar(dt=dt, symbol=symbol, kind="kline", data={"close": price}))
            for index, (symbol, price) in enumerate(prices.items())
        )
        broker.update_market_batch(TimeBatch(dt=dt, items=items))
    else:
        for symbol, price in prices.items():
            broker.on_new_price(symbol, price, dt)


@pytest.mark.parametrize(
    "qty, entry_price, exit_price, fee_rate, expected_pnl",
    [
        (1.0, 100.0, 120.0, 0.0, 20.0),
        (-1.0, 100.0, 90.0, 0.0, 10.0),
        (1.0, 100.0, 100.05, 0.001, -0.15005),
    ],
)
def test_broker_round_trip_equity_matches_hand_calculated_pnl(
    qty, entry_price, exit_price, fee_rate, expected_pnl
):
    """从 Broker 公共接口验证多空方向和往返手续费后的总权益。"""
    initial_cash = 1000.0
    broker = Broker(initial_cash=initial_cash, fee_rate=fee_rate)

    entry = broker.submit_market_order(
        "TEST",
        qty=qty,
        price=entry_price,
        price_dt="2026-01-01",
    )
    exit_order = broker.close_position(
        "TEST",
        price=exit_price,
        price_dt="2026-01-02",
    )

    gross_pnl = qty * (exit_price - entry_price)
    fees = abs(qty) * (entry_price + exit_price) * fee_rate

    assert entry.status == "filled"
    assert exit_order.status == "filled"
    assert broker.get_position_size("TEST") == 0
    assert broker.get_total_equity() == pytest.approx(initial_cash + gross_pnl - fees)
    assert broker.get_total_equity() == pytest.approx(initial_cash + expected_pnl)
    assert_pnl(broker.get_total_pnl(), realized=gross_pnl, fees=fees)
    assert_pnl(broker.get_pnl("TEST"), realized=gross_pnl, fees=fees)
    records = broker.get_pnl_records(symbol="TEST")
    assert len(records) == 2
    assert all(isinstance(record, PnlRecord) and record.reason == "trade" for record in records)
    assert [record.order_id for record in records] == [entry.id, exit_order.id]
    assert [record.qty for record in records] == [qty, -qty]
    assert [record.price for record in records] == [entry_price, exit_price]
    assert records[0].realized_pnl == 0
    assert records[0].fees == pytest.approx(abs(qty) * entry_price * fee_rate)
    assert records[1].realized_pnl == pytest.approx(gross_pnl)
    assert records[1].fees == pytest.approx(abs(qty) * exit_price * fee_rate)
    assert_account_reconciles(broker)


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("leverage", [1, 5])
def test_average_cost_partial_close_and_reversal(side, leverage):
    """手算均价 110 的加仓、减仓和双向反手，杠杆不改变毛盈亏和手续费。"""
    broker = Broker(initial_cash=1000, fee_rate=0.001, leverage=leverage)
    stages = [
        # 数量、成交价、累计毛盈亏、剩余未实现盈亏、累计手续费。
        (2, 100, 0, 0, 0.2),
        (1, 130, 0, 60, 0.33),
        (-1, 120, 10, 20, 0.45),
        (-4, 90, -30, 0, 0.81),
        (2, 80, -10, 0, 0.97),
    ]
    for index, (qty, price, realized, unrealized, fees) in enumerate(stages):
        order = broker.submit_market_order("TEST", qty=side * qty, price=price)
        assert order.status == "filled"
        assert_pnl(broker.get_total_pnl(), realized=side * realized, unrealized=side * unrealized, fees=fees)
        assert broker.get_pnl("TEST") == broker.get_total_pnl()
        assert len(broker.get_pnl_records(order_id=order.id)) == 1
        assert_account_reconciles(broker)
        if index == 3:
            assert broker.get_position_size("TEST") == -side * 2
            assert broker.get_position("TEST").cost_price == 90
            broker.on_new_price("TEST", 80)
            assert_pnl(broker.get_total_pnl(), realized=-side * 30, unrealized=side * 20, fees=0.81)
            assert_account_reconciles(broker)
    assert broker.get_position_size("TEST") == 0


def test_pnl_queries_are_immutable_snapshots_and_do_not_create_positions():
    """未知标的只读查询，旧快照不随行情变化，调用者不能篡改汇总或明细。"""
    broker = Broker(initial_cash=1000, fee_rate=0.001)
    assert broker.get_total_pnl("UNKNOWN") == Pnl()
    assert broker.get_pnl("UNKNOWN") == Pnl()
    assert broker.get_pnl_records(symbol="UNKNOWN") == []
    assert broker.portfolios["main"].positions == {}
    for query in (broker.get_pnl, broker.get_pnl_records):
        with pytest.raises(ValueError, match="portfolio not found"):
            query(portfolio="UNKNOWN")

    order = broker.submit_market_order("TEST", qty=1, price=100)
    snapshot = broker.get_total_pnl()
    records = broker.get_pnl_records()
    with pytest.raises(FrozenInstanceError):
        snapshot.fees = 0
    with pytest.raises(FrozenInstanceError):
        records[0].realized_pnl = 500
    records.clear()
    # 可变 Order 不是统计来源，改动查询到的订单不会改写已经完成的记账。
    order.qty = 900
    order.avg_price = 1
    broker.on_new_price("TEST", 110)
    assert_pnl(snapshot, fees=0.1)
    assert_pnl(broker.get_total_pnl(), unrealized=10, fees=0.1)
    assert len(broker.get_pnl_records()) == 1
    assert broker.get_pnl_records()[0].qty == 1
    assert broker.get_pnl_records(order_id="UNKNOWN") == []
    assert_account_reconciles(broker)


def test_multiple_portfolios_symbols_close_and_reuse_keep_original_pnl():
    """内部划拨、盈利分仓关闭和名称复用不能变成主分仓利润或丢失历史。"""
    broker = Broker(initial_cash=2000, fee_rate=0.001)
    broker.add_portfolio("trend", cash=600)
    broker.add_portfolio("hedge", cash=400)
    assert_pnl(broker.get_total_pnl())
    assert_pnl(broker.get_pnl())

    main = broker.submit_market_order("A", qty=2, price=100)
    trend = broker.submit_market_order("A", qty=-1, price=100, portfolio="trend")
    hedge = broker.submit_market_order("B", qty=1, price=50, portfolio="hedge")
    update_prices(broker, {"A": 120, "B": 55}, batch=True)
    assert_pnl(broker.get_pnl(), unrealized=40, fees=0.2)
    assert_pnl(broker.get_pnl(portfolio="trend"), unrealized=-20, fees=0.1)
    assert_pnl(broker.get_pnl(portfolio="hedge"), unrealized=5, fees=0.05)
    assert_pnl(broker.get_total_pnl("A"), unrealized=20, fees=0.3)
    assert_pnl(broker.get_total_pnl(), unrealized=25, fees=0.35)
    assert [record.order_id for record in broker.get_pnl_records()] == [main.id, trend.id, hedge.id]
    assert broker.get_pnl_records(portfolio="trend", symbol="B") == []
    assert broker.get_pnl_records(portfolio="hedge", symbol="B", order_id=hedge.id)[0].qty == 1
    assert_account_reconciles(broker)

    assert [order.status for order in broker.close_portfolio("trend")] == ["filled"]
    assert "trend" not in broker.get_portfolios()
    assert_pnl(broker.get_pnl(), unrealized=40, fees=0.2)
    assert_pnl(broker.get_pnl("A", portfolio="trend"), realized=-20, fees=0.22)
    assert_pnl(broker.get_total_pnl(), realized=-20, unrealized=45, fees=0.47)
    assert len(broker.get_pnl_records(portfolio="trend")) == 2
    assert_account_reconciles(broker)

    broker.add_portfolio("trend", cash=100)
    broker.submit_market_order("B", qty=1, price=55, portfolio="trend")
    broker.on_new_price("B", 60)
    assert_pnl(broker.get_pnl(portfolio="trend"), realized=-20, unrealized=5, fees=0.275)
    assert_account_reconciles(broker)
    broker.close_portfolio("trend")
    assert_pnl(broker.get_pnl(portfolio="trend"), realized=-15, fees=0.335)
    assert len(broker.get_pnl_records(portfolio="trend")) == 4
    assert_account_reconciles(broker)

    broker.close_portfolio("hedge")
    broker.close_portfolio("main")
    assert_pnl(broker.get_total_pnl(), realized=35, fees=0.885)
    assert broker.get_total_equity() == pytest.approx(2034.115)
    assert broker.get_pnl().net_pnl == pytest.approx(39.56)
    assert_account_reconciles(broker)


def test_closing_empty_portfolio_keeps_zero_result():
    """从未交易的分仓关闭后仍可查询，不将归还的本金计为利润。"""
    broker = Broker(initial_cash=1000)
    broker.add_portfolio("empty", cash=300)
    broker.close_portfolio("empty")
    assert broker.get_pnl(portfolio="empty") == Pnl()
    assert broker.get_pnl_records(portfolio="empty") == []
    assert_pnl(broker.get_total_pnl())
    assert_account_reconciles(broker)


def test_pending_rejected_canceled_and_skipped_orders_do_not_book_pnl():
    """挂单预检和无成交状态不记手续费，限价单真正成交时只记一次。"""
    broker = Broker(initial_cash=1000, fee_rate=0.001)
    broker.on_new_price("TEST", 100)
    pending = broker.submit_limit_order("TEST", qty=1, limit_price=90)
    assert pending.status == "pending"
    assert broker.get_pnl_records() == []
    assert_pnl(broker.get_total_pnl())

    rejected = broker.submit_market_order("TOO_BIG", qty=100, price=100)
    skipped = broker.order_target_size("TEST", 0)
    assert rejected.status == "rejected"
    assert skipped.status == "skipped"
    broker.cancel_order(pending.id)
    assert broker.get_pnl_records() == []

    filled = broker.submit_limit_order("TEST", qty=1, limit_price=90)
    broker.on_new_price("TEST", 89)
    broker.process_pending_orders()
    broker.process_pending_orders()
    assert filled.status == "filled"
    assert len(broker.get_pnl_records()) == 1
    record = broker.get_pnl_records(order_id=filled.id)[0]
    assert record.price == 90
    assert record.fees == pytest.approx(0.09)
    for order in (pending, rejected, skipped):
        assert broker.get_pnl_records(order_id=order.id) == []
    # 成本按限价 90，持仓按行情 89 估值，当批浮亏必须计入盈亏。
    assert_pnl(broker.get_total_pnl(), unrealized=-1, fees=0.09)
    assert_account_reconciles(broker)


def test_limit_order_rejected_on_trigger_does_not_add_pnl_record():
    """预检可通过但触发时资金不足的限价单，不收取未成交手续费。"""
    broker = Broker(initial_cash=1000, fee_rate=0.001)
    broker.on_new_price("TEST", 100)
    pending = broker.submit_limit_order("TEST", qty=1, limit_price=90)
    broker.submit_market_order("OTHER", qty=9.5, price=100)
    broker.on_new_price("TEST", 89)
    broker.process_pending_orders()
    assert pending.status == "rejected"
    assert broker.get_pnl_records(order_id=pending.id) == []
    assert len(broker.get_pnl_records()) == 1
    assert_pnl(broker.get_total_pnl(), fees=0.95)
    assert_account_reconciles(broker)


@pytest.mark.parametrize("margin_mode", ["cross", "isolated"])
def test_order_preview_isolates_trade_and_bankruptcy_statistics(margin_mode):
    """预检中的成交及穿仓清零只影响副本，不能写入真实分仓或 Broker 日志。"""
    broker = Broker(initial_cash=1000, fee_rate=0.001, leverage=10, margin_mode=margin_mode)
    broker.submit_market_order("TEST", qty=50, price=100)
    portfolio = broker.portfolios["main"]
    before = broker.get_total_pnl()
    records = broker.get_pnl_records()
    assert portfolio.can_submit_orders([{"symbol": "TEST", "qty": -25, "price": 110}]) == (True, None)
    assert portfolio.can_submit_orders([{"symbol": "TEST", "qty": -50, "price": 80}]) == (False, 0)
    assert broker.get_total_pnl() == before
    assert broker.get_pnl_records() == records
    assert portfolio.get_pnl_records() == records
    assert broker.get_position_size("TEST") == 50
    assert broker.get_total_equity() == 995
    assert_account_reconciles(broker)


def test_failed_atomic_close_does_not_book_previewed_trades():
    """关闭预检第二笔失败时，第一笔模拟成交不能计入真实已实现盈亏或手续费。"""
    broker = Broker(initial_cash=300, fee_rate=0.8, leverage=10)
    broker.submit_market_order("A", qty=10, price=10)
    broker.submit_market_order("B", qty=10, price=10)
    records = broker.get_pnl_records()
    assert [order.status for order in broker.close_portfolio("main")] == ["rejected"]
    assert broker.get_pnl_records() == records
    assert broker.get_position_sizes() == {"A": 10, "B": 10}
    assert_pnl(broker.get_total_pnl(), fees=160)
    assert_account_reconciles(broker)


def test_exit_rule_records_actual_closing_order():
    """订单退出条件触发的平仓使用同一记账路径和订单关联。"""
    broker = Broker(initial_cash=1000, fee_rate=0.001)
    broker.submit_market_order("TEST", qty=2, price=100, stop_loss_price=90)
    broker.on_new_price("TEST", 90)
    broker.check_exit_rules()
    assert_pnl(broker.get_total_pnl(), realized=-20, fees=0.38)
    records = broker.get_pnl_records()
    assert len(records) == 2
    assert broker.get_order(records[-1].order_id).source == "close_position"
    assert_account_reconciles(broker)


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize(
    "mode, qty, price, realized, fees, adjustment",
    [
        ("isolated", 10, 91, -90, 1, 0),
        ("isolated", 10, 80, -200, 1, 100),
        ("cross", 50, 81, -950, 5, 0),
        ("cross", 50, 79, -1050, 5, 55),
    ],
)
def test_liquidation_and_bankruptcy_follow_actual_equity(mode, qty, price, realized, fees, adjustment, batch, side):
    """强平不增收手续费，穿仓保留毛亏损和结算调整，最终结果对齐实际权益。"""
    qty *= side
    if side < 0:
        price = 200 - price  # 空头上涨与多头下跌具有相同的单位毛亏损。
    broker = Broker(initial_cash=1000, fee_rate=0.001, leverage=10, margin_mode=mode)
    broker.submit_market_order("TEST", qty=qty, price=100)
    update_prices(broker, {"TEST": price}, batch=batch)
    assert broker.get_position_size("TEST") == 0
    assert_pnl(broker.get_total_pnl(), realized=realized, fees=fees, adjustment=adjustment)
    assert_account_reconciles(broker)

    records = broker.get_pnl_records()
    close = records[1]
    assert close.reason == ("bankruptcy" if adjustment else "liquidation")
    assert close.qty == -qty
    assert close.price == price
    assert close.order_id is None
    assert close.fees == 0
    assert close.dt == datetime(2026, 1, 2, tzinfo=timezone.utc)
    if mode == "cross" and adjustment:
        assert len(records) == 3
        settlement = records[2]
        assert settlement.reason == "bankruptcy_settlement"
        assert settlement.symbol is None
        assert settlement.qty == 0
        assert settlement.price is None
        assert settlement.dt == close.dt
        assert_pnl(broker.get_total_pnl("TEST"), realized=realized, fees=fees)
    else:
        assert len(records) == 2
        assert broker.get_total_pnl("TEST") == broker.get_total_pnl()
    update_prices(broker, {"TEST": price}, batch=batch)
    assert broker.get_pnl_records() == records
    assert_account_reconciles(broker)


def test_isolated_batch_records_all_bankrupt_and_liquidated_positions():
    """同批次首个仓位穿仓后，其余仓位的强平仍完整记账。"""
    broker = Broker(initial_cash=10000, fee_rate=0.001, leverage=10, margin_mode="isolated")
    broker.submit_market_order("BANKRUPT", qty=10, price=100)
    broker.submit_market_order("LIQUIDATE", qty=10, price=100)
    update_prices(broker, {"BANKRUPT": 80, "LIQUIDATE": 91}, batch=True)
    assert_pnl(broker.get_total_pnl("BANKRUPT"), realized=-200, fees=1, adjustment=100)
    assert_pnl(broker.get_total_pnl("LIQUIDATE"), realized=-90, fees=1)
    assert_pnl(broker.get_total_pnl(), realized=-290, fees=2, adjustment=100)
    assert broker.get_total_equity() == 9808
    assert len(broker.get_pnl_records()) == 4
    assert_account_reconciles(broker)


def test_cross_bankruptcy_keeps_symbol_losses_and_account_settlement_separate():
    """全仓同时有赢有亏时，不把账户债务清零调整人为归到盈利或亏损标的。"""
    broker = Broker(initial_cash=1000, fee_rate=0.001, leverage=10)
    broker.submit_market_order("LOSS", qty=40, price=100)
    broker.submit_market_order("GAIN", qty=10, price=100)
    update_prices(broker, {"LOSS": 70, "GAIN": 110}, batch=True)
    assert_pnl(broker.get_total_pnl("LOSS"), realized=-1200, fees=4)
    assert_pnl(broker.get_total_pnl("GAIN"), realized=100, fees=1)
    assert_pnl(broker.get_total_pnl(), realized=-1100, fees=5, adjustment=105)
    assert broker.get_total_pnl().net_pnl == -1000
    records = broker.get_pnl_records()
    broker.portfolios["main"].mark_bankrupt()
    assert broker.get_pnl_records() == records
    assert_account_reconciles(broker)


def test_rejected_order_price_can_trigger_independent_real_risk_settlement():
    """显式下单价格触发真实穿仓时，拒绝订单不记成交，系统结算仍需保留。"""
    broker = Broker(initial_cash=1000, fee_rate=0.001, leverage=10)
    entry = broker.submit_market_order("TEST", qty=50, price=100)
    rejected = broker.submit_market_order("TEST", qty=-50, price=79)
    assert rejected.status == "rejected"
    assert broker.get_pnl_records(order_id=rejected.id) == []
    assert [record.order_id for record in broker.get_pnl_records()] == [entry.id, None, None]
    assert_pnl(broker.get_total_pnl(), realized=-1050, fees=5, adjustment=55)
    assert_account_reconciles(broker)


def test_bankrupt_portfolio_can_be_archived_and_name_reused_without_losing_adjustment():
    """关闭穿仓分仓后保存原结算调整，同名新分仓的成交继续累计并对齐总权益。"""
    broker = Broker(initial_cash=1000, fee_rate=0.001, leverage=10)
    broker.add_portfolio("alt", cash=300)
    broker.submit_market_order("TEST", qty=25, price=100, portfolio="alt")
    broker.on_new_price("TEST", 88)
    broker.close_portfolio("alt")
    assert_pnl(broker.get_pnl(portfolio="alt"), realized=-300, fees=2.5, adjustment=2.5)
    assert broker.get_total_equity() == 700
    assert_account_reconciles(broker)

    broker.add_portfolio("alt", cash=200)
    broker.submit_market_order("TEST", qty=1, price=90, portfolio="alt")
    broker.on_new_price("TEST", 95)
    broker.close_portfolio("alt")
    assert_pnl(broker.get_total_pnl(), realized=-295, fees=2.685, adjustment=2.5)
    assert broker.get_pnl(portfolio="alt") == broker.get_total_pnl()
    assert broker.get_pnl() == Pnl()
    assert_account_reconciles(broker)


def test_standalone_portfolio_reset_clears_pnl_and_records():
    """独立 Portfolio 的重置重新开始统计，旧不可变快照仍保留原结果。"""
    portfolio = Portfolio(initial_cash=1000, fee_rate=0.001)
    portfolio.submit_order("TEST", qty=1, price=100)
    portfolio.close_position("TEST", last_price=110)
    pnl = portfolio.get_pnl()
    records = portfolio.get_pnl_records()
    assert_pnl(pnl, realized=10, fees=0.21)
    portfolio.reset()
    assert portfolio.get_pnl() == Pnl()
    assert portfolio.get_pnl_records() == []
    assert portfolio.get_portfolio_equity() == 1000
    assert len(records) == 2
    assert_pnl(pnl, realized=10, fees=0.21)
