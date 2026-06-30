import inspect

import minbt
import pytest
from minbt import Broker, Exchange, ExitConfig, Strategy


POSITIONAL = inspect.Parameter.POSITIONAL_OR_KEYWORD
KEYWORD_ONLY = inspect.Parameter.KEYWORD_ONLY


def _parameters(callable_obj):
    return {
        name: parameter
        for name, parameter in inspect.signature(callable_obj).parameters.items()
        if name != "self"
    }


def _assert_parameter_contract(callable_obj, positional, keyword_only):
    parameters = _parameters(callable_obj)
    assert list(parameters) == [*positional, *keyword_only]
    assert all(parameters[name].kind is POSITIONAL for name in positional)
    assert all(parameters[name].kind is KEYWORD_ONLY for name in keyword_only)


def test_exchange_public_signatures_match_design():
    _assert_parameter_contract(
        Exchange.set_bars,
        ["data"],
        ["date_key", "symbol_key", "price_key"],
    )
    _assert_parameter_contract(
        Exchange.set_books,
        ["data"],
        ["date_key", "symbol_key", "price_key"],
    )
    _assert_parameter_contract(
        Exchange.set_trades,
        ["data"],
        ["date_key", "symbol_key", "price_key"],
    )
    _assert_parameter_contract(Exchange.set_news, ["data"], ["date_key"])
    assert list(_parameters(Exchange.run)) == []
    assert not hasattr(Exchange, "set_data")


def test_broker_constructor_signature_matches_design():
    _assert_parameter_contract(
        Broker.__init__,
        ["initial_cash", "fee_rate"],
        [
            "leverage",
            "margin_mode",
            "warning_margin_level",
            "min_margin_level",
            "market",
            "logger",
        ],
    )
    parameters = _parameters(Broker.__init__)
    assert parameters["leverage"].default == 1.0
    assert parameters["margin_mode"].default == "cross"
    assert parameters["warning_margin_level"].default == 0.2
    assert parameters["min_margin_level"].default == 0.1
    assert parameters["market"].default is None
    assert parameters["logger"].default is None


def test_broker_order_signatures_match_design():
    exit_parameters = [
        "stop_loss_price",
        "take_profit_price",
        "trailing_stop_pct",
        "trailing_stop_amount",
    ]
    _assert_parameter_contract(
        Broker.submit_market_order,
        ["symbol", "qty", "price"],
        ["leverage", "price_dt", "portfolio", *exit_parameters],
    )
    _assert_parameter_contract(
        Broker.submit_limit_order,
        ["symbol", "qty", "limit_price"],
        ["price_dt", "portfolio", *exit_parameters],
    )
    for method, target_name in (
        (Broker.order_target_size, "target_size"),
        (Broker.order_target_value, "target_value"),
        (Broker.order_target_percent, "target_percent"),
    ):
        _assert_parameter_contract(
            method,
            ["symbol", target_name, "price"],
            ["leverage", "price_dt", "portfolio", *exit_parameters],
        )
    _assert_parameter_contract(
        Broker.close_position,
        ["symbol", "price"],
        ["price_dt", "portfolio"],
    )
    _assert_parameter_contract(Broker.close_portfolio, ["portfolio"], [])
    assert _parameters(Broker.close_portfolio)["portfolio"].default is inspect.Parameter.empty


def test_broker_exit_signatures_match_design():
    _assert_parameter_contract(
        Broker.set_exit,
        ["order_id"],
        [
            "stop_loss_price",
            "take_profit_price",
            "trailing_stop_pct",
            "trailing_stop_amount",
        ],
    )
    _assert_parameter_contract(
        Broker.clear_exit,
        ["order_id"],
        ["stop_loss_price", "take_profit_price", "trailing_stop", "custom"],
    )
    _assert_parameter_contract(
        Broker.add_exit,
        ["order_id"],
        ["name", "condition", "state"],
    )
    _assert_parameter_contract(Broker.get_exit, ["order_id"], [])


def test_broker_query_signatures_match_design():
    _assert_parameter_contract(Broker.get_order, ["order_id"], [])
    _assert_parameter_contract(Broker.get_orders, [], ["portfolio", "symbol"])
    _assert_parameter_contract(
        Broker.get_active_order,
        ["symbol"],
        ["portfolio"],
    )
    _assert_parameter_contract(Broker.get_equity, ["portfolio"], [])
    _assert_parameter_contract(Broker.get_cash, ["portfolio", "include_locked"], [])
    _assert_parameter_contract(Broker.get_position, ["symbol", "portfolio"], [])
    _assert_parameter_contract(Broker.get_position_size, ["symbol", "portfolio"], [])
    _assert_parameter_contract(Broker.get_position_sizes, ["portfolio"], [])
    _assert_parameter_contract(Broker.get_positions, ["portfolio"], [])


def test_public_defaults_match_design():
    bars = _parameters(Exchange.set_bars)
    assert bars["date_key"].default == "dt"
    assert bars["symbol_key"].default == "symbol"
    assert bars["price_key"].default == "close"

    market_order = _parameters(Broker.submit_market_order)
    assert market_order["price"].default is None
    assert market_order["leverage"].default is None
    assert market_order["price_dt"].default is None
    assert market_order["portfolio"].default is None

    cash = _parameters(Broker.get_cash)
    assert cash["portfolio"].default is None
    assert cash["include_locked"].default is False

    clear_exit = _parameters(Broker.clear_exit)
    assert all(
        clear_exit[name].default is True
        for name in ("stop_loss_price", "take_profit_price", "trailing_stop", "custom")
    )


def test_internal_control_parameters_are_not_public():
    for method in (
        Broker.submit_market_order,
        Broker.submit_limit_order,
        Broker.order_target_size,
        Broker.order_target_value,
        Broker.order_target_percent,
    ):
        parameters = _parameters(method)
        assert "source" not in parameters
        assert "normalize_qty" not in parameters
        assert "create_if_missing" not in parameters


def test_strategy_and_package_do_not_export_legacy_entry_points():
    for name in ("on_data", "on_bar", "market_buy", "market_sell", "market_order"):
        assert not hasattr(Strategy, name)
    for name in ("MarketModel", "SimpleMarket", "CryptoMarket", "ChinaAStockMarket"):
        assert not hasattr(minbt, name)


def test_exit_config_fields_match_design():
    assert list(ExitConfig.__dataclass_fields__) == [
        "order_id",
        "symbol",
        "portfolio",
        "active",
        "stop_loss_price",
        "take_profit_price",
        "trailing_stop_pct",
        "trailing_stop_amount",
        "trailing_anchor",
        "custom_rules",
    ]


def test_get_active_order_rejects_unknown_portfolio():
    broker = Broker(initial_cash=1000, fee_rate=0)

    with pytest.raises(ValueError, match="portfolio not found"):
        broker.get_active_order("TEST", portfolio="missing")
