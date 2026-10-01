from datetime import datetime, timezone

import pandas as pd
import pytest

from minbt import Bar, Broker, Exchange, News, Strategy
from minbt.data.model import normalize_datetime


UTC = timezone.utc


def _dt(day=1, minute=0):
    return datetime(2026, 1, day, 0, minute, tzinfo=UTC)


class BarsStrategy(Strategy):
    def on_init(self):
        self.calls = []

    def on_bars(self, dt, bars):
        self.calls.append((dt, bars, self.broker.get_last_price("A") if self.broker else None))


def test_set_bars_sorts_rows_and_emits_one_complete_time_slice():
    exchange = Exchange()
    strategy = BarsStrategy("bars", Broker(initial_cash=1000))
    exchange.set_bars(
        pd.DataFrame(
            [
                {"dt": _dt(2), "symbol": "B", "close": 201.0},
                {"dt": _dt(1), "symbol": "A", "close": 100.0},
                {"dt": _dt(2), "symbol": "A", "close": 101.0},
                {"dt": _dt(1), "symbol": "B", "close": 200.0},
            ]
        )
    )
    exchange.add_strategy(strategy)

    exchange.run(load_mode="incremental")

    assert [(dt, list(bars), price) for dt, bars, price in strategy.calls] == [
        (_dt(1), ["A", "B"], 100.0),
        (_dt(2), ["B", "A"], 101.0),
    ]
    assert exchange.get_current_dt() == _dt(2)


def test_normalize_datetime_accepts_explicit_timestamp_unit():
    explicit_ms = normalize_datetime(1_000_000_000, unit="ms")
    assert explicit_ms == datetime(1970, 1, 12, 13, 46, 40, tzinfo=UTC)
    with pytest.raises(ValueError, match="unit"):
        normalize_datetime(1_000, unit="minutes")


def test_set_bars_rejects_replacing_custom_feed_with_reserved_name():
    class CustomBarsFeed:
        name = "bars"

        def events(self):
            return iter(())

    exchange = Exchange()
    exchange.add_feed(CustomBarsFeed())

    with pytest.raises(ValueError, match="cannot be replaced"):
        exchange.set_bars([{"dt": _dt(), "symbol": "A", "close": 100}])


def test_kline_does_not_require_complete_ohlcv():
    exchange = Exchange()
    strategy = BarsStrategy("partial", Broker(initial_cash=1000))
    exchange.set_bars([{"dt": _dt(), "symbol": "A", "close": 100.0}])
    exchange.add_strategy(strategy)

    exchange.run()

    assert dict(strategy.calls[0][1]["A"]) == {"close": 100.0}


def test_bar_payload_is_read_only():
    exchange = Exchange()
    strategy = BarsStrategy("readonly", Broker(initial_cash=1000))
    exchange.set_bars([{"dt": _dt(), "symbol": "A", "close": 100.0}])
    exchange.add_strategy(strategy)
    exchange.run()

    with pytest.raises(TypeError):
        strategy.calls[0][1]["A"]["close"] = 101.0


def test_same_time_callbacks_follow_family_order_and_news_does_not_mark_price():
    class FeedStrategy(Strategy):
        def on_init(self):
            self.calls = []

        def on_bars(self, dt, bars):
            self.calls.append(("bars", self.broker.get_last_price("A")))

        def on_books(self, dt, books):
            self.calls.append(("books", self.broker.get_last_price("A")))

        def on_trades(self, dt, trades):
            self.calls.append(("trades", self.broker.get_last_price("A")))

        def on_news(self, dt, news):
            self.calls.append(("news", self.broker.get_last_price("A"), news[0].symbol))

    broker = Broker(initial_cash=1000, mark_price="kline.close")
    strategy = FeedStrategy("families", broker)
    exchange = Exchange()
    exchange.set_news([{"dt": _dt(), "symbol": "A", "headline": "hello"}])
    exchange.set_trades([{"dt": _dt(), "symbol": "A", "price": 102.0}])
    exchange.set_books([{"dt": _dt(), "symbol": "A", "mid": 101.0}])
    exchange.set_bars([{"dt": _dt(), "symbol": "A", "close": 100.0}])
    exchange.add_strategy(strategy)

    exchange.run()

    assert strategy.calls == [
        ("bars", 100.0),
        ("books", 100.0),
        ("trades", 100.0),
        ("news", 100.0, "A"),
    ]


def test_broker_can_choose_orderbook_mark_price():
    class Probe(Strategy):
        def on_init(self):
            self.price_seen = None

        def on_bars(self, dt, bars):
            self.price_seen = self.broker.get_last_price("A")

    broker = Broker(initial_cash=1000, mark_price="orderbook.mid")
    strategy = Probe("book-mark", broker)
    exchange = Exchange()
    exchange.set_bars([{"dt": _dt(), "symbol": "A", "close": 100.0}])
    exchange.set_books([{"dt": _dt(), "symbol": "A", "mid": 101.5}])
    exchange.add_strategy(strategy)

    exchange.run()

    assert strategy.price_seen == 101.5


def test_trade_mark_requires_explicit_aggregation():
    exchange = Exchange()
    exchange.set_trades(
        [
            {"dt": _dt(), "symbol": "A", "price": 100.0},
            {"dt": _dt(), "symbol": "A", "price": 101.0},
        ]
    )
    exchange.add_strategy(Strategy("trade-error", Broker(initial_cash=1000, mark_price="trade.price")))

    with pytest.raises(ValueError, match="multiple mark prices"):
        exchange.run()


def test_trade_mark_can_choose_last_value():
    class Probe(Strategy):
        def on_init(self):
            self.price = None

        def on_trades(self, dt, trades):
            self.price = self.broker.get_last_price("A")

    broker = Broker(
        initial_cash=1000,
        mark_price="trade.price",
        mark_price_aggregation="last",
    )
    strategy = Probe("trade-last", broker)
    exchange = Exchange()
    exchange.set_trades(
        [
            {"dt": _dt(), "symbol": "A", "price": 100.0},
            {"dt": _dt(), "symbol": "A", "price": 101.0},
        ]
    )
    exchange.add_strategy(strategy)

    exchange.run()

    assert strategy.price == 101.0


def test_missing_mark_price_error_explains_how_to_fix_configuration():
    class EnterOnFirstBar(Strategy):
        def on_init(self):
            self.entered = False

        def on_bars(self, dt, bars):
            if not self.entered:
                self.broker.submit_market_order("A", qty=1, price=100.0)
                self.entered = True

    broker = Broker(initial_cash=1000, mark_price="kline.close", mark_price_missing="error")
    exchange = Exchange()
    exchange.set_bars(
        [
            {"dt": _dt(1), "symbol": "A", "close": 100.0},
            {"dt": _dt(2), "symbol": "A", "open": 101.0},
        ]
    )
    exchange.add_strategy(EnterOnFirstBar("missing-mark", broker))

    with pytest.raises(ValueError, match="mark_price='orderbook.mid'"):
        exchange.run()


def test_custom_price_bar_can_drive_broker_without_price_priority():
    class PriceFeed:
        name = "mark-feed"
        feed_priority = 10
        supports_preload = True
        supports_incremental = True
        ordered = True
        replayable = True

        def events(self):
            yield Bar(_dt(), "A", "price", {"value": 123.0, "source": "mark"})

        def prepare(self):
            return None

        def close(self):
            return None

    broker = Broker(initial_cash=1000, mark_price="price.value")
    strategy = Strategy("price-bar", broker)
    exchange = Exchange()
    exchange.add_feed(PriceFeed())
    exchange.add_strategy(strategy)

    exchange.run()

    assert broker.get_last_price("A") == 123.0


def test_feed_priority_orders_callback_groups_and_same_priority_warns():
    class CaptureLogger:
        def __init__(self):
            self.warnings = []

        def info(self, *args, **kwargs):
            return None

        def warning(self, message, *args, **kwargs):
            self.warnings.append(message % args if args else message)

        def exception(self, *args, **kwargs):
            return None

    class Feed:
        supports_preload = True
        supports_incremental = True
        ordered = True
        replayable = True

        def __init__(self, name, close):
            self.name = name
            self.close_value = close

        def events(self):
            yield Bar(_dt(), "A", "kline", {"close": self.close_value})

        def prepare(self):
            return None

        def close(self):
            return None

    class Probe(Strategy):
        def on_init(self):
            self.calls = []

        def on_bars(self, dt, bars):
            self.calls.append(bars["A"]["close"])

    logger = CaptureLogger()
    exchange = Exchange(logger=logger)
    exchange.add_feed(Feed("low", 100), feed_priority=1)
    exchange.add_feed(Feed("high", 101), feed_priority=2)
    exchange.add_feed(Feed("same", 102), feed_priority=1)
    strategy = Probe("priority", Broker(initial_cash=1000, mark_price=None))
    exchange.add_strategy(strategy)

    exchange.run()

    assert strategy.calls == [101, 100, 102]
    assert len(logger.warnings) == 1
    assert "same-priority feed overlap" in logger.warnings[0]


def test_custom_bar_callback_stays_after_trades():
    class CustomFeed:
        name = "custom"
        supports_preload = True
        supports_incremental = True
        ordered = True
        replayable = True

        def events(self):
            yield Bar(_dt(), "A", "signal", {"value": 1})

    class TradeFeed:
        name = "trade"
        supports_preload = True
        supports_incremental = True
        ordered = True
        replayable = True

        def events(self):
            yield Bar(_dt(), "A", "trade", {"price": 100.0, "qty": 1.0})

    class Probe(Strategy):
        def on_init(self):
            self.calls = []

        def on_trades(self, dt, trades):
            self.calls.append("trade")

        def on_bar(self, dt, bar):
            self.calls.append("custom")

    exchange = Exchange()
    exchange.add_feed(CustomFeed())
    exchange.add_feed(TradeFeed())
    strategy = Probe("callback-order", Broker(initial_cash=1000, mark_price=None))
    exchange.add_strategy(strategy)

    exchange.run()

    assert strategy.calls == ["trade", "custom"]


def test_duplicate_kline_rows_are_rejected():
    exchange = Exchange()
    with pytest.raises(ValueError, match="duplicate"):
        exchange.set_bars(
            [
                {"dt": _dt(), "symbol": "A", "close": 100},
                {"dt": _dt(), "symbol": "A", "close": 101},
            ]
        )


def test_exchange_requires_bar_or_news_from_feed():
    class BadFeed:
        name = "bad"
        feed_priority = 0
        supports_preload = True
        supports_incremental = True
        ordered = True
        replayable = True

        def events(self):
            yield {"dt": _dt()}

    exchange = Exchange()
    exchange.add_feed(BadFeed())
    exchange.add_strategy(Strategy("bad", Broker(initial_cash=1000, mark_price=None)))

    with pytest.raises(TypeError, match="must yield Bar or News"):
        exchange.run()


def test_news_is_not_a_bar():
    event = News(_dt(), {"headline": "x"})
    assert event.symbol is None
    assert not isinstance(event, Bar)


@pytest.mark.parametrize("value", [None, float("nan"), "NaT"])
def test_invalid_datetime_values_are_rejected(value):
    with pytest.raises(ValueError, match="invalid datetime"):
        normalize_datetime(value)


def test_bar_rejects_missing_kind_and_symbol():
    with pytest.raises(ValueError, match="kind must not be None"):
        Bar(_dt(), "A", None, {})
    with pytest.raises(ValueError, match="symbol must not be None"):
        Bar(_dt(), None, "kline", {})


def test_set_bars_rejects_missing_symbol_value():
    with pytest.raises(ValueError, match="symbol must not be None"):
        Exchange().set_bars([{"dt": _dt(), "symbol": None, "close": 100.0}])
