import os
import inspect
import subprocess
import sys
from pathlib import Path

import pytest
from pytest import approx

from minbt import Broker, Market, markets


def test_submit_market_order_returns_filled_order():
    broker = Broker(initial_cash=10000, fee_rate=0.001)

    order = broker.submit_market_order("BTCUSDT", qty=1.0, price=5000.0)

    assert order.status == "filled"
    assert order.order_type == "market"
    assert order.source == "submit_market_order"
    assert order.filled_qty == 1.0
    assert order.avg_price == 5000.0
    assert broker.get_market_price("BTCUSDT") == 5000.0
    assert broker.get_position("BTCUSDT").size == 1.0
    assert approx(broker.get_cash()) == 10000 - 5000 * (1 + 0.001)


def test_submit_market_order_raises_when_market_price_is_missing():
    broker = Broker(initial_cash=1000, fee_rate=0)

    with pytest.raises(ValueError, match="market price not found"):
        broker.submit_market_order("AAPL", qty=1)

    assert broker.get_orders() == []
    assert broker.get_position("AAPL") is None


def test_submit_market_order_requires_existing_portfolio_before_price_update():
    broker = Broker(initial_cash=1000, fee_rate=0)

    with pytest.raises(ValueError):
        broker.submit_market_order("AAPL", qty=1, price=100, portfolio="missing")

    assert broker.last_prices == {}
    assert broker.portfolios["main"].positions == {}


def test_position_size_query_does_not_create_empty_position():
    broker = Broker(initial_cash=1000, fee_rate=0)

    assert broker.get_position_size("UNKNOWN") == 0
    assert broker.get_position("UNKNOWN") is None
    assert broker.portfolios["main"].positions == {}


def test_add_portfolio_transfers_cash_from_main():
    broker = Broker(initial_cash=1000, fee_rate=0)
    broker.add_portfolio("alt", cash=300)

    assert broker.get_portfolios() == ["main", "alt"]
    assert broker.get_all_portfolio_equity() == 1000
    assert broker.get_total_equity() == 1000
    assert broker.get_equity() == 700
    assert broker.get_equity(portfolio="alt") == 300


def test_add_portfolio_rejects_duplicate_or_insufficient_cash():
    broker = Broker(initial_cash=1000, fee_rate=0)
    broker.add_portfolio("alt", cash=300)

    with pytest.raises(ValueError):
        broker.add_portfolio("alt", cash=100)
    with pytest.raises(ValueError):
        broker.add_portfolio("too_big", cash=800)

    assert broker.get_cash() == 700
    assert broker.get_cash(portfolio="alt") == 300


def test_close_empty_non_main_portfolio_returns_cash_to_main():
    broker = Broker(initial_cash=1000, fee_rate=0)
    broker.add_portfolio("alt", cash=300)

    orders = broker.close_portfolio("alt")

    assert len(orders) == 1
    assert orders[0].status == "skipped"
    assert broker.get_portfolios() == ["main"]
    assert broker.get_cash() == 1000
    assert broker.get_total_equity() == 1000


def test_submit_market_order_supports_portfolio():
    broker = Broker(initial_cash=1000, fee_rate=0)
    broker.add_portfolio("alt", cash=300)

    order = broker.submit_market_order("AAPL", qty=1, price=100, portfolio="alt")

    assert order.status == "filled"
    assert broker.get_position_size("AAPL") == 0
    assert broker.get_position_size("AAPL", portfolio="alt") == 1
    assert broker.get_cash(portfolio="alt") == 200


def test_order_target_interfaces_return_order():
    broker = Broker(initial_cash=1000, fee_rate=0)

    order = broker.order_target_percent("BTCUSDT", 0.5, price=100)
    assert order.status == "filled"
    assert order.source == "target_percent"
    assert broker.get_position_size("BTCUSDT") == 5
    assert broker.get_cash() == 500

    order = broker.order_target_size("BTCUSDT", 2, price=100)
    assert order.status == "filled"
    assert order.source == "target_size"
    assert broker.get_position_size("BTCUSDT") == 2
    assert broker.get_cash() == 800

    order = broker.order_target_value("BTCUSDT", 0, price=100)
    assert order.status == "filled"
    assert order.source == "target_value"
    assert broker.get_position_size("BTCUSDT") == 0

    order = broker.order_target_size("BTCUSDT", 0, price=100)
    assert order.status == "skipped"


def test_order_target_percent_uses_explicit_price_for_equity():
    broker = Broker(initial_cash=1000, fee_rate=0)

    broker.submit_market_order("BTCUSDT", qty=5, price=100)
    order = broker.order_target_percent("BTCUSDT", 0.5, price=200)

    assert order.status == "filled"
    assert broker.get_position_size("BTCUSDT") == pytest.approx(3.75)


def test_submit_limit_order_can_fill_and_cancel():
    broker = Broker(initial_cash=1000, fee_rate=0)
    broker.on_new_price("AAPL", 100, "2026-01-01")

    order = broker.submit_limit_order("AAPL", qty=1, limit_price=95)
    assert order.status == "pending"
    broker.on_new_price("AAPL", 96, "2026-01-02")
    broker.process_pending_orders(dt="2026-01-02")
    assert order.status == "pending"

    broker.on_new_price("AAPL", 94, "2026-01-03")
    broker.process_pending_orders(dt="2026-01-03")
    assert order.status == "filled"
    assert order.avg_price == 95
    assert broker.get_position_size("AAPL") == 1

    pending = broker.submit_limit_order("AAPL", qty=1, limit_price=90)
    canceled = broker.cancel_order(pending.id)
    assert canceled.status == "canceled"
    assert canceled.source == "cancel_order"
    assert pending.status == "canceled"
    broker.on_new_price("AAPL", 89, "2026-01-04")
    broker.process_pending_orders(dt="2026-01-04")
    assert broker.get_position_size("AAPL") == 1


def test_cancel_order_returns_clear_result_for_done_order():
    broker = Broker(initial_cash=1000, fee_rate=0)

    filled_order = broker.submit_market_order("AAPL", qty=1, price=100)
    order_count = len(broker.get_orders())
    cancel_result = broker.cancel_order(filled_order.id)

    assert filled_order.status == "filled"
    assert cancel_result is filled_order
    assert cancel_result.status == "filled"
    assert len(broker.get_orders()) == order_count


def test_submit_limit_order_does_not_expose_source_parameter():
    signature = inspect.signature(Broker.submit_limit_order)

    assert "source" not in signature.parameters


def test_order_attached_take_profit_closes_position():
    broker = Broker(initial_cash=1000, fee_rate=0)

    order = broker.submit_market_order("BTCUSDT", qty=1, price=100, take_profit_price=110)
    broker.on_new_price("BTCUSDT", 112, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")

    assert order.status == "filled"
    assert broker.get_position_size("BTCUSDT") == 0
    assert broker.get_cash() == 1012


def test_set_exit_updates_attached_stop_loss_by_order_id():
    broker = Broker(initial_cash=1000, fee_rate=0)

    order = broker.submit_market_order(
        "BTCUSDT",
        qty=1,
        price=100,
        stop_loss_price=95,
        take_profit_price=120,
    )
    broker.on_new_price("BTCUSDT", 106, "2026-01-02")
    config = broker.set_exit(order.id, stop_loss_price=104)
    broker.on_new_price("BTCUSDT", 103, "2026-01-03")
    broker.check_exit_rules(dt="2026-01-03")

    assert config.stop_loss_price == 104
    assert broker.get_position_size("BTCUSDT") == 0
    assert broker.get_cash() == 1003


def test_clear_exit_removes_attached_rules():
    broker = Broker(initial_cash=1000, fee_rate=0)

    order = broker.submit_market_order("BTCUSDT", qty=1, price=100, take_profit_price=110)
    config = broker.clear_exit(order.id)
    broker.on_new_price("BTCUSDT", 112, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")

    assert not config.active
    assert broker.get_position_size("BTCUSDT") == 1
    assert broker.get_cash() == 900


def test_trailing_stop_closes_after_pullback():
    broker = Broker(initial_cash=1000, fee_rate=0)

    order = broker.submit_market_order("BTCUSDT", qty=1, price=100, trailing_stop_pct=0.1)
    broker.on_new_price("BTCUSDT", 120, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")
    assert broker.get_position_size("BTCUSDT") == 1

    broker.on_new_price("BTCUSDT", 107, "2026-01-03")
    broker.check_exit_rules(dt="2026-01-03")

    assert broker.get_exit(order.id).active is False
    assert broker.get_position_size("BTCUSDT") == 0
    assert broker.get_cash() == 1007


def test_custom_exit_condition_uses_exit_context():
    broker = Broker(initial_cash=1000, fee_rate=0)
    order = broker.submit_market_order("BTCUSDT", qty=1, price=100)

    def exit_if_price_breaks(ctx):
        return ctx.order_id == order.id and ctx.price < 98

    broker.add_exit(order.id, condition=exit_if_price_breaks)
    broker.on_new_price("BTCUSDT", 97, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")

    assert broker.get_position_size("BTCUSDT") == 0
    assert broker.get_cash() == 997


def test_exit_trailing_modes_are_mutually_exclusive():
    broker = Broker(initial_cash=1000, fee_rate=0)

    with pytest.raises(ValueError, match="cannot both be set"):
        broker.submit_market_order(
            "BTCUSDT",
            qty=1,
            price=100,
            trailing_stop_pct=0.1,
            trailing_stop_amount=5,
        )

    assert broker.get_orders() == []


def test_a_stock_market_locks_same_day_buy():
    broker = Broker(initial_cash=100000, fee_rate=0, market=markets.A_STOCK)

    buy = broker.submit_market_order("600519.SH", qty=100, price=100, price_dt="2026-01-05")
    position = broker.get_position("600519.SH")
    assert buy.status == "filled"
    assert position.size == 100
    assert position.available_size == 0
    assert position.locked_size == 100

    close = broker.close_position("600519.SH", price=99, price_dt="2026-01-05")
    assert close.status == "rejected"
    assert broker.get_position_size("600519.SH") == 100

    broker.on_new_price("600519.SH", 101, "2026-01-06")
    assert position.available_size == 100
    assert position.locked_size == 0
    close = broker.close_position("600519.SH", price=101, price_dt="2026-01-06")
    assert close.status == "filled"
    assert broker.get_position_size("600519.SH") == 0


def test_a_stock_market_requires_dt_for_manual_order():
    broker = Broker(initial_cash=100000, fee_rate=0, market=markets.A_STOCK)

    order = broker.submit_market_order("600519.SH", qty=100, price=100)

    assert order.status == "rejected"
    assert broker.get_position_size("600519.SH") == 0


def test_market_preset_is_copied_per_broker():
    broker_a = Broker(initial_cash=100000, fee_rate=0, market=markets.A_STOCK)
    broker_b = Broker(initial_cash=100000, fee_rate=0, market=markets.A_STOCK)

    market_snapshot = broker_a.get_market("600519.SH")
    market_snapshot.allow_short = True

    assert markets.A_STOCK.allow_short is False
    assert broker_a.get_market("600519.SH").allow_short is False
    assert broker_b.get_market("600519.SH").allow_short is False


def test_broker_routes_market_rules_by_symbol():
    broker = Broker(initial_cash=100000, fee_rate=0, market=markets.CRYPTO)
    broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH", "510300.SH"])

    non_lot = broker.submit_market_order("510300.SH", qty=150, price=100, price_dt="2026-01-05")
    assert non_lot.status == "rejected"
    assert broker.get_position_size("510300.SH") == 0

    a_buy = broker.submit_market_order("600519.SH", qty=100, price=100, price_dt="2026-01-05")
    crypto_buy = broker.submit_market_order("BTCUSDT", qty=0.123, price=100, price_dt="2026-01-05")
    crypto_close = broker.close_position("BTCUSDT", price=100, price_dt="2026-01-05")
    a_same_day_close = broker.close_position("600519.SH", price=100, price_dt="2026-01-05")

    assert a_buy.status == "filled"
    assert broker.get_position("600519.SH").locked_size == 100
    assert crypto_buy.status == "filled"
    assert crypto_close.status == "filled"
    assert broker.get_position_size("BTCUSDT") == 0
    assert a_same_day_close.status == "rejected"
    assert "insufficient available position" in a_same_day_close.reason
    assert broker.get_position_size("600519.SH") == 100

    broker.on_new_price("BTCUSDT", 101, "2026-01-06")
    assert broker.get_position("600519.SH").available_size == 100
    a_next_day_close = broker.close_position("600519.SH", price=101, price_dt="2026-01-06")
    assert a_next_day_close.status == "filled"


def test_broker_routes_target_and_limit_orders_by_symbol_market():
    broker = Broker(initial_cash=100000, fee_rate=0, market=markets.CRYPTO)
    broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])

    a_target = broker.order_target_value("600519.SH", target_value=8050, price=13, price_dt="2026-01-05")
    assert a_target.status == "filled"
    assert broker.get_position_size("600519.SH") == 600

    broker.on_new_price("ETHUSDT", 100, "2026-01-05")
    crypto_limit = broker.submit_limit_order("ETHUSDT", qty=0.125, limit_price=95)
    assert crypto_limit.status == "pending"

    broker.on_new_price("ETHUSDT", 94, "2026-01-05")
    broker.process_pending_orders(dt="2026-01-05")
    assert crypto_limit.status == "filled"
    assert broker.get_position_size("ETHUSDT") == pytest.approx(0.125)


def test_get_market_returns_snapshot():
    broker = Broker(initial_cash=100000, fee_rate=0, market=markets.CRYPTO)
    broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])

    a_market = broker.get_market("600519.SH")
    default_market = broker.get_market("BTCUSDT")
    a_market.allow_short = True
    default_market.allow_short = False

    assert a_market.name == "AStock"
    assert default_market.name == "Crypto"
    assert broker.get_market("600519.SH").allow_short is False
    assert broker.get_market("BTCUSDT").allow_short is True


def test_add_market_rejects_ambiguous_or_runtime_routes():
    broker = Broker(initial_cash=100000, fee_rate=0, market=markets.CRYPTO)

    with pytest.raises(ValueError, match="conflicts with default market"):
        broker.add_market("Crypto", markets.A_STOCK, symbols=["600519.SH"])

    with pytest.raises(ValueError, match="symbols must be non-empty"):
        broker.add_market("Empty", markets.A_STOCK, symbols=[])

    with pytest.raises(ValueError, match="duplicate symbols"):
        broker.add_market("Dup", markets.A_STOCK, symbols=["600519.SH", "600519.SH"])

    broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])

    with pytest.raises(ValueError, match="market already exists"):
        broker.add_market("AStock", markets.A_STOCK, symbols=["510300.SH"])

    with pytest.raises(ValueError, match="symbol already mapped"):
        broker.add_market("Other", markets.CRYPTO, symbols=["600519.SH"])

    running_broker = Broker(initial_cash=100000, fee_rate=0, market=markets.CRYPTO)
    running_broker.submit_market_order("BTCUSDT", qty=1, price=100, price_dt="2026-01-05")
    with pytest.raises(ValueError, match="before broker has orders"):
        running_broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])


def test_a_stock_market_normalizes_target_value_to_lot_size():
    broker = Broker(initial_cash=100000, fee_rate=0, market=markets.A_STOCK)

    order = broker.order_target_value("600519.SH", target_value=80000, price=13, price_dt="2026-01-05")

    assert order.status == "filled"
    assert broker.get_position_size("600519.SH") == 6100


def test_a_stock_market_rejects_explicit_non_lot_market_order():
    broker = Broker(initial_cash=100000, fee_rate=0, market=markets.A_STOCK)

    order = broker.submit_market_order("600519.SH", qty=150, price=100, price_dt="2026-01-05")

    assert order.status == "rejected"
    assert broker.get_position_size("600519.SH") == 0


def test_t1_market_locks_only_new_long_size_when_reversing_short_to_long():
    market = Market(name="T1Short", t_plus=1, allow_short=True)
    broker = Broker(initial_cash=100000, fee_rate=0, market=market)

    short_order = broker.submit_market_order("TEST", qty=-100, price=10, price_dt="2026-01-05")
    reverse_order = broker.submit_market_order("TEST", qty=150, price=9, price_dt="2026-01-06")
    position = broker.get_position("TEST")

    assert short_order.status == "filled"
    assert reverse_order.status == "filled"
    assert position.size == 50
    assert position.locked_size == 50
    assert position.available_size == 0

    same_day_close = broker.close_position("TEST", price=9, price_dt="2026-01-06")
    assert same_day_close.status == "rejected"

    broker.on_new_price("TEST", 9, "2026-01-07")
    assert position.available_size == 50
    next_day_close = broker.close_position("TEST", price=9, price_dt="2026-01-07")
    assert next_day_close.status == "filled"


def test_t1_market_rejects_cross_zero_sale_of_locked_long_position():
    market = Market(name="T1Short", t_plus=1, allow_short=True)
    broker = Broker(initial_cash=100000, fee_rate=0, market=market)

    broker.submit_market_order("TEST", qty=100, price=10, price_dt="2026-01-05")
    reverse_order = broker.submit_market_order("TEST", qty=-150, price=10, price_dt="2026-01-05")

    assert reverse_order.status == "rejected"
    assert "insufficient available position" in reverse_order.reason
    assert broker.get_position_size("TEST") == 100


def test_limit_order_rejects_insufficient_cash_at_submission():
    broker = Broker(initial_cash=100, fee_rate=0)
    broker.on_new_price("AAPL", 10, "2026-01-01")

    order = broker.submit_limit_order("AAPL", qty=20, limit_price=10)

    assert order.status == "rejected"
    assert order.id not in broker._pending_order_ids


def test_limit_order_exit_validation_is_atomic_when_position_direction_changes():
    broker = Broker(initial_cash=1000, fee_rate=0)
    broker.on_new_price("TEST", 110, "2026-01-01")
    pending = broker.submit_limit_order("TEST", qty=1, limit_price=100, stop_loss_price=95)
    broker.submit_market_order("TEST", qty=-2, price=110, price_dt="2026-01-01")

    broker.on_new_price("TEST", 99, "2026-01-02")
    broker.process_pending_orders(dt="2026-01-02")

    assert pending.status == "rejected"
    assert "exit conditions invalid at fill" in pending.reason
    assert broker.get_position_size("TEST") == -2
    assert broker.get_exit(pending.id) is None
    assert pending.id not in broker._pending_order_ids


def test_limit_order_rejects_atomically_when_cash_is_spent_before_fill():
    broker = Broker(initial_cash=1000, fee_rate=0)
    broker.on_new_price("LIMIT", 110, "2026-01-01")
    pending = broker.submit_limit_order("LIMIT", qty=5, limit_price=100)
    broker.submit_market_order("OTHER", qty=8, price=100, price_dt="2026-01-01")

    broker.on_new_price("LIMIT", 99, "2026-01-02")
    broker.process_pending_orders(dt="2026-01-02")

    assert pending.status == "rejected"
    assert broker.get_position_size("LIMIT") == 0
    assert broker.get_position_size("OTHER") == 8
    assert pending.id not in broker._pending_order_ids
    assert pending.id not in broker._pending_exit_params


def test_limit_order_activates_valid_exit_config_after_fill():
    broker = Broker(initial_cash=1000, fee_rate=0)
    broker.on_new_price("TEST", 110, "2026-01-01")
    pending = broker.submit_limit_order(
        "TEST",
        qty=1,
        limit_price=100,
        stop_loss_price=90,
        trailing_stop_pct=0.1,
    )

    broker.on_new_price("TEST", 99, "2026-01-02")
    broker.process_pending_orders(dt="2026-01-02")
    config = broker.get_exit(pending.id)

    assert pending.status == "filled"
    assert pending.avg_price == 100
    assert config.active is True
    assert config.stop_loss_price == 90
    assert config.trailing_anchor == 100
    assert broker.get_active_order("TEST") is pending


def test_close_portfolio_preflight_prevents_partial_close():
    broker = Broker(initial_cash=300, fee_rate=0.8, leverage=10)
    broker.submit_market_order("A", qty=10, price=10)
    broker.submit_market_order("B", qty=10, price=10)

    orders = broker.close_portfolio("main")

    assert [order.status for order in orders] == ["rejected"]
    assert broker.get_position_sizes() == {"A": 10, "B": 10}


def test_expired_order_cannot_control_reopened_position():
    broker = Broker(initial_cash=1000, fee_rate=0)
    old_order = broker.submit_market_order("TEST", qty=1, price=100)
    broker.close_position("TEST", price=100)
    broker.submit_market_order("TEST", qty=1, price=100)

    with pytest.raises(ValueError, match="no longer associated"):
        broker.set_exit(old_order.id, stop_loss_price=90)
    with pytest.raises(ValueError, match="no longer associated"):
        broker.add_exit(old_order.id, condition=lambda ctx: False)


def test_position_lifecycle_keeps_same_side_orders_and_expires_them_on_reversal():
    broker = Broker(initial_cash=1000, fee_rate=0)
    entry = broker.submit_market_order("TEST", qty=2, price=100)
    reduction = broker.order_target_size("TEST", target_size=1, price=100)

    broker.set_exit(entry.id, stop_loss_price=90)
    broker.set_exit(reduction.id, stop_loss_price=90)
    reversal = broker.submit_market_order("TEST", qty=-2, price=100)

    with pytest.raises(ValueError, match="no longer associated"):
        broker.set_exit(entry.id, stop_loss_price=110)
    with pytest.raises(ValueError, match="no longer associated"):
        broker.set_exit(reduction.id, stop_loss_price=110)

    config = broker.set_exit(reversal.id, stop_loss_price=110)
    assert config.active is True
    assert broker.get_position_size("TEST") == -1


def test_callable_exit_state_is_initialized_once_and_persists():
    broker = Broker(initial_cash=1000, fee_rate=0)
    order = broker.submit_market_order("TEST", qty=1, price=100)
    factory_calls = 0

    def state_factory():
        nonlocal factory_calls
        factory_calls += 1
        return {}

    def exit_after_two_checks(ctx):
        ctx.state["checks"] = ctx.state.get("checks", 0) + 1
        return ctx.state["checks"] >= 2

    broker.add_exit(order.id, condition=exit_after_two_checks, state=state_factory)
    broker.on_new_price("TEST", 101, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")
    broker.on_new_price("TEST", 102, "2026-01-03")
    broker.check_exit_rules(dt="2026-01-03")

    assert factory_calls == 1
    assert broker.get_position_size("TEST") == 0


def test_exit_config_is_public_snapshot():
    broker = Broker(initial_cash=1000, fee_rate=0)
    order = broker.submit_market_order("TEST", qty=1, price=100, stop_loss_price=90)
    broker.add_exit(order.id, condition=lambda ctx: False, name="custom")

    config = broker.get_exit(order.id)
    config.stop_loss_price = 80

    assert config.symbol == "TEST"
    assert config.portfolio == "main"
    assert config.custom_rules == ("custom",)
    assert broker.get_exit(order.id).stop_loss_price == 90


def test_new_exit_config_deactivates_previous_config_for_same_position():
    broker = Broker(initial_cash=1000, fee_rate=0)
    first = broker.submit_market_order("TEST", qty=1, price=100, stop_loss_price=90)
    second = broker.submit_market_order("TEST", qty=1, price=100, stop_loss_price=80)

    assert broker.get_exit(first.id).active is False
    assert broker.get_exit(second.id).active is True
    assert broker.get_active_order("TEST") is second


def test_liquidation_expires_active_exit_order():
    broker = Broker(initial_cash=1000, fee_rate=0, leverage=10)
    order = broker.submit_market_order("TEST", qty=50, price=100, stop_loss_price=90)

    broker.on_new_price("TEST", 80, "2026-01-02")
    broker.check_exit_rules(dt="2026-01-02")

    assert broker.get_position_size("TEST") == 0
    assert broker.get_exit(order.id).active is False
    assert broker.get_active_order("TEST") is None
    with pytest.raises(ValueError, match="no longer associated"):
        broker.set_exit(order.id, stop_loss_price=70)


def test_order_queries_support_filters_and_do_not_create_positions():
    broker = Broker(initial_cash=1000, fee_rate=0)
    broker.add_portfolio("alt", cash=300)
    main_order = broker.submit_market_order("MAIN", qty=1, price=100)
    alt_order = broker.submit_market_order("ALT", qty=1, price=100, portfolio="alt")

    assert broker.get_orders(portfolio="alt") == [alt_order]
    assert broker.get_orders(symbol="MAIN") == [main_order]
    assert broker.get_position("UNKNOWN", "alt") is None
    assert broker.get_positions("alt") == {"ALT": broker.get_position("ALT", "alt")}
    assert broker.get_cash("alt") == 200


def test_close_portfolio_respects_market_rules():
    broker = Broker(initial_cash=100000, fee_rate=0, market=markets.A_STOCK)

    broker.submit_market_order("600519.SH", qty=100, price=100, price_dt="2026-01-05")
    same_day_orders = broker.close_portfolio("main")
    assert same_day_orders[0].status == "rejected"
    assert "main" in broker.portfolios
    assert broker.get_position_size("600519.SH") == 100

    broker.on_new_price("600519.SH", 101, "2026-01-06")
    next_day_orders = broker.close_portfolio("main")
    assert next_day_orders[0].status == "filled"
    assert "main" in broker.portfolios
    assert broker.get_position_size("600519.SH") == 0


def test_broker_rejects_invalid_margin_config():
    with pytest.raises(ValueError):
        Broker(initial_cash=1000, fee_rate=0, warning_margin_level=0.1, min_margin_level=0.1)

    with pytest.raises(ValueError):
        Broker(initial_cash=1000, fee_rate=0, warning_margin_level=1.0, min_margin_level=0.1)


def test_broker_validation_survives_optimized_python():
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    code = """
from minbt import Broker
try:
    Broker(initial_cash=-1, fee_rate=2, leverage=0)
except ValueError:
    raise SystemExit(0)
raise SystemExit(1)
"""

    result = subprocess.run(
        [sys.executable, "-O", "-c", code],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_add_market_rejects_when_only_price_state_exists():
    broker = Broker(initial_cash=100000, fee_rate=0, market=markets.CRYPTO)
    broker.on_new_price("BTCUSDT", 100, "2026-01-05")

    with pytest.raises(ValueError, match="before broker has orders"):
        broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])


def test_add_market_rejects_after_position_history_exists():
    broker = Broker(initial_cash=100000, fee_rate=0, market=markets.CRYPTO)
    broker.submit_market_order("BTCUSDT", qty=1, price=100, price_dt="2026-01-05")
    broker.close_position("BTCUSDT", price=100, price_dt="2026-01-06")

    with pytest.raises(ValueError, match="before broker has orders"):
        broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])


def test_add_market_rejects_non_market_or_string_symbols():
    broker = Broker(initial_cash=100000, fee_rate=0, market=markets.CRYPTO)

    with pytest.raises(TypeError, match="market must be a Market instance"):
        broker.add_market("Bad", "not a market", symbols=["X"])

    with pytest.raises(TypeError, match="symbols must be a non-empty list"):
        broker.add_market("Bad2", markets.A_STOCK, symbols="600519.SH")

    with pytest.raises(TypeError, match="symbols must be a non-empty list"):
        broker.add_market("Bad3", markets.A_STOCK, symbols=None)


def test_t1_unlock_is_isolated_across_markets():
    t1_default = Market(name="T1Default", t_plus=1, allow_short=True)
    broker = Broker(initial_cash=100000, fee_rate=0, market=t1_default)
    broker.add_market(
        "T1Other",
        Market(name="T1Other", t_plus=1, allow_short=True),
        symbols=["OTHER"],
    )

    broker.submit_market_order("DEFAULT", qty=100, price=10, price_dt="2026-01-05")
    broker.submit_market_order("OTHER", qty=100, price=10, price_dt="2026-01-05")
    default_pos = broker.get_position("DEFAULT")
    other_pos = broker.get_position("OTHER")
    assert default_pos.locked_size == 100
    assert other_pos.locked_size == 100

    broker.on_new_price("DEFAULT", 11, "2026-01-06")

    assert default_pos.available_size == 100
    assert other_pos.available_size == 100


def test_symbols_for_market_is_not_mutated_by_custom_market_on_new_dt():
    class MutatingMarket(Market):
        def on_new_dt(self, broker, dt, symbols=None):
            if symbols is not None:
                symbols.clear()

    broker = Broker(initial_cash=100000, fee_rate=0, market=Market(name="Crypto", t_plus=0))
    broker.add_market(
        "Mutating",
        MutatingMarket(name="Mutating", t_plus=1, allow_short=True),
        symbols=["LOCKED"],
    )

    assert broker._symbols_for_market("Mutating") == ["LOCKED"]

    broker.on_new_price("LOCKED", 11, "2026-01-06")

    assert broker._symbols_for_market("Mutating") == ["LOCKED"]
