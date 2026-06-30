import os
import subprocess
import sys
from pathlib import Path

import pytest
from pytest import approx

from minbt import Broker, markets


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


def test_submit_market_order_rejects_missing_price_as_order():
    broker = Broker(initial_cash=1000, fee_rate=0)

    order = broker.submit_market_order("AAPL", qty=1)

    assert order.status == "rejected"
    assert "market price not found" in order.reason
    assert broker.get_position("AAPL", create_if_missing=False) is None


def test_submit_market_order_requires_existing_portfolio_before_price_update():
    broker = Broker(initial_cash=1000, fee_rate=0)

    with pytest.raises(ValueError):
        broker.submit_market_order("AAPL", qty=1, price=100, portfolio="missing")

    assert broker.last_prices == {}
    assert broker.portfolios["main"].positions == {}


def test_position_size_query_does_not_create_empty_position():
    broker = Broker(initial_cash=1000, fee_rate=0)

    assert broker.get_position_size("UNKNOWN") == 0
    assert broker.get_position("UNKNOWN", create_if_missing=False) is None
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
    broker.on_new_price("AAPL", 89, "2026-01-04")
    broker.process_pending_orders(dt="2026-01-04")
    assert broker.get_position_size("AAPL") == 1


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

    broker.add_exit(order.id, exit_if_price_breaks)
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

    broker_a.market.allow_short = True

    assert markets.A_STOCK.allow_short is False
    assert broker_b.market.allow_short is False


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
