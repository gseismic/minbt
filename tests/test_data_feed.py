from datetime import datetime, timezone
import sqlite3

import pytest

from minbt import Broker, Exchange, Strategy
from minbt.data import binance
from minbt.data.feed import FeedEvent


class FeedCaptureStrategy(Strategy):
    def on_init(self):
        self.calls = []

    def on_bars(self, dt, bars):
        self.calls.append((dt, list(bars), self.broker.get_last_price("BTCUSDT")))


class SimpleBarsFeed:
    name = "simple-bars"
    event_type = "bars"

    def events(self):
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        yield FeedEvent(
            event_type="bars",
            dt=dt,
            data={
                "BTCUSDT": {
                    "dt": dt,
                    "symbol": "BTCUSDT",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 10.0,
                }
            },
            prices={"BTCUSDT": 100.5},
        )


def _ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _fake_kline(open_time, close):
    return {
        "open_time": open_time,
        "open": close - 1,
        "high": close + 1,
        "low": close - 2,
        "close": close,
        "volume": 12.0,
        "close_time": open_time + 59_999,
        "volume_quote": 1200.0,
        "num_trades": 42.0,
        "volume_base_buy": 6.0,
        "volume_quote_buy": 600.0,
        "ignored": "0",
    }


class FakeBinanceClient:
    def __init__(self, rows=None, fail=False):
        self.rows = rows or []
        self.fail = fail
        self.calls = []

    def fetch_klines(self, symbol, period, start_dt, end_dt, chunk_size=1000, delay=0.5):
        self.calls.append((symbol, period, start_dt, end_dt, chunk_size, delay))
        if self.fail:
            raise AssertionError("client should not be called")
        return list(self.rows)


def test_exchange_add_feed_runs_bars_feed():
    exchange = Exchange()
    broker = Broker(initial_cash=1000, fee_rate=0)
    strategy = FeedCaptureStrategy(strategy_id="feed", broker=broker)

    exchange.add_feed(SimpleBarsFeed())
    exchange.add_strategy(strategy)
    exchange.run()

    expected_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert strategy.calls == [(expected_dt, ["BTCUSDT"], 100.5)]


def test_exchange_add_feed_rejects_duplicate_bar_symbol_at_same_dt():
    dt = datetime(2024, 1, 1, tzinfo=timezone.utc)

    class DuplicateFeed(SimpleBarsFeed):
        name = "duplicate-bars"

        def events(self):
            yield FeedEvent(
                event_type="bars",
                dt=dt,
                data={"BTCUSDT": {"dt": dt, "symbol": "BTCUSDT", "close": 101.0}},
                prices={"BTCUSDT": 101.0},
            )

    exchange = Exchange()
    exchange.set_bars([{"dt": dt, "symbol": "BTCUSDT", "close": 100.0}])
    exchange.add_feed(DuplicateFeed())
    exchange.add_strategy(Strategy(strategy_id="s", broker=Broker(initial_cash=1000, fee_rate=0)))

    with pytest.raises(ValueError, match="duplicate"):
        exchange.run()


def test_exchange_add_feed_rejects_price_conflict_inside_event():
    dt = datetime(2024, 1, 1, tzinfo=timezone.utc)

    class ConflictFeed(SimpleBarsFeed):
        name = "conflict-bars"

        def events(self):
            yield FeedEvent(
                event_type="bars",
                dt=dt,
                data={"BTCUSDT": {"dt": dt, "symbol": "BTCUSDT", "close": 100.0}},
                prices={"BTCUSDT": 101.0},
            )

    exchange = Exchange()
    exchange.add_feed(ConflictFeed())
    exchange.add_strategy(Strategy(strategy_id="s", broker=Broker(initial_cash=1000, fee_rate=0)))

    with pytest.raises(ValueError, match="price conflict"):
        exchange.run()


def test_binance_bars_replay_feed_downloads_and_reuses_cache(tmp_path):
    start = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    second = datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 0, 2, tzinfo=timezone.utc)
    first_client = FakeBinanceClient(rows=[_fake_kline(_ms(start), 100.0), _fake_kline(_ms(second), 101.0)])
    feed = binance.BarsReplayFeed(
        symbols=["btcusdt"],
        interval="1m",
        start=start,
        end=end,
        cache_dir=tmp_path,
    )
    feed._client = first_client

    events = list(feed.events())

    assert len(first_client.calls) == 1
    assert [event.dt for event in events] == [start, second]
    assert events[0].data["BTCUSDT"]["close"] == 100.0
    assert events[0].data["BTCUSDT"]["num_trades"] == 42
    assert (tmp_path / "minbt-data.sqlite3").exists()

    cached_feed = binance.BarsReplayFeed(
        symbols=["BTCUSDT"],
        interval="1m",
        start=start,
        end=end,
        cache_dir=tmp_path,
        cache_only=True,
    )
    cached_feed._client = FakeBinanceClient(fail=True)

    cached_events = list(cached_feed.events())

    assert [event.data["BTCUSDT"]["close"] for event in cached_events] == [100.0, 101.0]


def test_binance_bars_replay_feed_supports_only_futures(tmp_path):
    with pytest.raises(ValueError, match="futures"):
        binance.BarsReplayFeed(
            symbols=["BTCUSDT"],
            interval="1m",
            start="2024-01-01",
            end="2024-01-02",
            cache_dir=tmp_path,
            market="spot",
        )


def test_binance_cache_only_does_not_create_empty_database(tmp_path):
    feed = binance.BarsReplayFeed(
        symbols=["BTCUSDT"],
        interval="1m",
        start="2024-01-01",
        end="2024-01-02",
        cache_dir=tmp_path,
        cache_only=True,
    )

    with pytest.raises(RuntimeError, match="does not exist"):
        feed.prepare()

    assert not (tmp_path / "minbt-data.sqlite3").exists()


def test_binance_closed_only_does_not_mark_unclosed_range_as_covered(tmp_path, monkeypatch):
    start = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    second = datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 0, 2, tzinfo=timezone.utc)
    client = FakeBinanceClient(rows=[_fake_kline(_ms(start), 100.0), _fake_kline(_ms(second), 101.0)])
    monkeypatch.setattr(binance.time, "time", lambda: _ms(second) / 1000)
    feed = binance.BarsReplayFeed(
        symbols=["BTCUSDT"],
        interval="1m",
        start=start,
        end=end,
        cache_dir=tmp_path,
    )
    feed._client = client

    events = list(feed.events())

    assert [event.dt for event in events] == [start]
    with sqlite3.connect(tmp_path / "minbt-data.sqlite3") as conn:
        coverage = conn.execute("SELECT start_ms, end_ms FROM bar_coverage").fetchone()
    assert coverage == (_ms(start), _ms(second))
