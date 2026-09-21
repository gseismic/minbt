from datetime import datetime, timezone

import pytest

from minbt import Bar, Broker, Exchange, Strategy


UTC = timezone.utc


def _dt(minute):
    return datetime(2026, 1, 1, 0, minute, tzinfo=UTC)


class ListFeed:
    supports_preload = True
    supports_incremental = True
    ordered = True
    replayable = True

    def __init__(self, name, events, *, feed_priority=0):
        self.name = name
        self.feed_priority = feed_priority
        self._events = list(events)
        self.read_count = 0
        self.closed_count = 0

    def prepare(self):
        return None

    def events(self):
        for event in self._events:
            self.read_count += 1
            yield event

    def close(self):
        self.closed_count += 1


class CaptureStrategy(Strategy):
    def on_init(self):
        self.observations = []
        self.equities = []

    def on_bars(self, dt, bars):
        self.observations.append((dt, bars["A"]["close"], self.broker.get_last_price("A")))

    def _record_broker_history(self):
        super()._record_broker_history()
        self.equities.append(self.broker.get_total_equity())


def _make_feed(name="bars"):
    return ListFeed(
        name,
        [
            Bar(_dt(0), "A", "kline", {"close": 100.0}),
            Bar(_dt(1), "A", "kline", {"close": 101.0}),
            Bar(_dt(2), "A", "kline", {"close": 102.0}),
        ],
    )


def _run(mode):
    exchange = Exchange()
    exchange.add_feed(_make_feed())
    strategy = CaptureStrategy("capture", Broker(initial_cash=1000))
    exchange.add_strategy(strategy)
    exchange.run(load_mode=mode)
    return strategy


def test_preload_and_incremental_produce_same_result():
    preload = _run("preload")

    incremental = _run("incremental")

    assert preload.observations == incremental.observations
    assert preload.equities == incremental.equities


def test_auto_prefers_incremental_for_ordered_feed():
    feed = _make_feed()
    exchange = Exchange()
    exchange.add_feed(feed)
    strategy = CaptureStrategy("auto", Broker(initial_cash=1000))
    exchange.add_strategy(strategy)

    exchange.run()

    assert strategy.observations[0][1] == 100.0
    assert feed.read_count == 3


def test_incremental_requires_ordered_feed():
    class UnorderedFeed(ListFeed):
        ordered = False

    feed = UnorderedFeed("unordered", [Bar(_dt(0), "A", "kline", {"close": 100})])
    exchange = Exchange()
    exchange.add_feed(feed)
    exchange.add_strategy(Strategy("s", Broker(initial_cash=1000)))

    with pytest.raises(ValueError, match="load_mode='incremental'"):
        exchange.run(load_mode="incremental")


def test_auto_falls_back_to_preload_for_unordered_feed():
    class UnorderedFeed(ListFeed):
        supports_incremental = False
        ordered = False

    feed = UnorderedFeed(
        "unordered",
        [
            Bar(_dt(1), "A", "kline", {"close": 101}),
            Bar(_dt(0), "A", "kline", {"close": 100}),
        ],
    )
    exchange = Exchange()
    exchange.add_feed(feed)
    strategy = CaptureStrategy("preload", Broker(initial_cash=1000))
    exchange.add_strategy(strategy)

    exchange.run()

    assert [row[1] for row in strategy.observations] == [100, 101]


def test_preload_mode_releases_feed_after_reading():
    feed = _make_feed()
    exchange = Exchange()
    exchange.add_feed(feed)
    exchange.add_strategy(CaptureStrategy("preload", Broker(initial_cash=1000)))

    exchange.run(load_mode="preload")

    assert feed.closed_count >= 1


def test_broker_receives_one_complete_batch_per_dt():
    class BatchBroker(Broker):
        def __init__(self):
            super().__init__(initial_cash=1000)
            self.batch_sizes = []

        def update_market_batch(self, batch):
            self.batch_sizes.append((batch.dt, len(batch.items)))
            return super().update_market_batch(batch)

    class PriceFeed(ListFeed):
        def __init__(self):
            super().__init__("price", [Bar(_dt(0), "A", "price", {"value": 100.5})])

    exchange = Exchange()
    exchange.set_bars([{"dt": _dt(0), "symbol": "A", "close": 100.0}])
    exchange.add_feed(PriceFeed())
    broker = BatchBroker()
    exchange.add_strategy(Strategy("batch", broker))

    exchange.run()

    assert broker.batch_sizes == [(_dt(0), 2)]


def test_feed_is_closed_when_event_iteration_fails():
    class BrokenFeed(ListFeed):
        def events(self):
            yield Bar(_dt(0), "A", "kline", {"close": 100})
            raise RuntimeError("source failed")

    feed = BrokenFeed("broken", [])
    exchange = Exchange()
    exchange.add_feed(feed)
    exchange.add_strategy(Strategy("broken", Broker(initial_cash=1000)))

    with pytest.raises(RuntimeError, match="source failed"):
        exchange.run()

    assert feed.closed_count >= 1


def test_feed_is_replayable_and_can_run_twice():
    feed = _make_feed()
    exchange = Exchange()
    exchange.add_feed(feed)
    first = CaptureStrategy("first", Broker(initial_cash=1000))
    exchange.add_strategy(first)
    exchange.run()
    second = CaptureStrategy("second", Broker(initial_cash=1000))
    exchange.add_strategy(second)
    exchange.run()

    assert first.observations == second.observations


def test_non_replayable_feed_rejects_second_run():
    class OneShotFeed(ListFeed):
        replayable = False

    feed = OneShotFeed("one-shot", [Bar(_dt(0), "A", "kline", {"close": 100})])
    exchange = Exchange()
    exchange.add_feed(feed)
    exchange.add_strategy(Strategy("one", Broker(initial_cash=1000)))
    exchange.run()

    with pytest.raises(RuntimeError, match="cannot be run again"):
        exchange.run()


def test_out_of_order_incremental_source_fails_before_late_callback():
    class BadFeed(ListFeed):
        pass

    feed = BadFeed(
        "bad",
        [
            Bar(_dt(0), "A", "kline", {"close": 100}),
            Bar(_dt(2), "A", "kline", {"close": 102}),
            Bar(_dt(1), "A", "kline", {"close": 101}),
        ],
    )
    exchange = Exchange()
    exchange.add_feed(feed)
    strategy = CaptureStrategy("bad", Broker(initial_cash=1000))
    exchange.add_strategy(strategy)

    with pytest.raises(ValueError, match="not ordered"):
        exchange.run(load_mode="incremental")

    assert [row[1] for row in strategy.observations] == [100]
