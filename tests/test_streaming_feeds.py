from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from minbt import Broker, Exchange, Strategy
from minbt.data import CsvBarsFeed, IosqlBarsFeed
from minbt.data.feed import FeedEvent


UTC = timezone.utc


def _csv_row(open_time, close):
    return [
        str(open_time),
        str(close - 1),
        str(close + 1),
        str(close - 2),
        str(close),
        "10",
        str(open_time + 59_999),
        "100",
        "42",
        "5",
        "50",
        "0",
    ]


def _write_csv(path: Path, rows, *, header=True):
    lines = []
    if header:
        lines.append(
            "open_time,open,high,low,close,volume,close_time,"
            "quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore"
        )
    lines.extend(",".join(row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_csv_bars_feed_reads_monthly_files_incrementally(tmp_path):
    start_ms = 1_672_531_200_000
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-01.csv",
        [_csv_row(start_ms, 100), _csv_row(start_ms + 60_000, 101)],
    )
    _write_csv(
        tmp_path / "ETHUSDT-1m-2023-01.csv",
        [_csv_row(start_ms, 200), _csv_row(start_ms + 60_000, 201)],
        header=False,
    )

    feed = CsvBarsFeed(
        tmp_path,
        symbols=["BTCUSDT", "ETHUSDT"],
        start="2023-01-01T00:00:00Z",
        end="2023-01-01T00:02:00Z",
    )

    assert feed.name.startswith("csv:bars:")
    events = feed.events()
    first = next(events)
    assert list(first.data) == ["BTCUSDT", "ETHUSDT"]
    assert first.data["BTCUSDT"]["close"] == 100.0
    assert first.data["ETHUSDT"]["num_trades"] == 42
    second = next(events)
    assert second.dt > first.dt
    with pytest.raises(StopIteration):
        next(events)


def test_csv_bars_feed_rejects_out_of_order_rows(tmp_path):
    start_ms = 1_672_531_200_000
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-01.csv",
        [_csv_row(start_ms + 60_000, 101), _csv_row(start_ms, 100)],
    )
    feed = CsvBarsFeed(tmp_path, symbols="BTCUSDT")

    with pytest.raises(ValueError, match="not ordered"):
        list(feed.events())


def test_csv_bars_feed_rejects_missing_months(tmp_path):
    start_ms = 1_672_531_200_000
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-01.csv",
        [_csv_row(start_ms, 100)],
    )
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-03.csv",
        [_csv_row(start_ms + 86400_000 * 59, 300)],
    )
    feed = CsvBarsFeed(
        tmp_path,
        symbols="BTCUSDT",
        start="2023-01-01T00:00:00Z",
        end="2023-04-01T00:00:00Z",
    )

    with pytest.raises(FileNotFoundError, match="BTCUSDT@2023-02"):
        list(feed.events())


def test_csv_bars_feed_uses_start_when_checking_missing_months(tmp_path):
    march_ms = 1_677_628_800_000
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-03.csv",
        [_csv_row(march_ms, 300)],
    )
    feed = CsvBarsFeed(
        tmp_path,
        symbols="BTCUSDT",
        start="2023-01-01T00:00:00Z",
    )

    with pytest.raises(FileNotFoundError, match="BTCUSDT@2023-01"):
        list(feed.events())


def test_csv_bars_feed_rejects_partially_missing_requested_symbols(tmp_path):
    start_ms = 1_672_531_200_000
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-01.csv",
        [_csv_row(start_ms, 100)],
    )
    feed = CsvBarsFeed(
        tmp_path,
        symbols=["BTCUSDT", "ETHUSDT"],
        interval="1m",
    )

    with pytest.raises(FileNotFoundError, match="ETHUSDT"):
        list(feed.events())


def test_csv_bars_feed_rejects_symbol_without_rows_in_requested_range(tmp_path):
    start_ms = 1_672_531_200_000
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-01.csv",
        [_csv_row(start_ms, 100)],
    )
    _write_csv(
        tmp_path / "ETHUSDT-1m-2023-01.csv",
        [_csv_row(start_ms + 86_400_000, 200)],
    )
    feed = CsvBarsFeed(
        tmp_path,
        symbols=["BTCUSDT", "ETHUSDT"],
        start="2023-01-01T00:00:00Z",
        end="2023-01-01T00:01:00Z",
        interval="1m",
    )

    with pytest.raises(ValueError, match="ETHUSDT"):
        list(feed.events())


def test_csv_bars_feed_rejects_range_without_rows(tmp_path):
    start_ms = 1_672_531_200_000
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-01.csv",
        [_csv_row(start_ms, 100)],
    )
    feed = CsvBarsFeed(
        tmp_path,
        symbols="BTCUSDT",
        start="2023-02-01T00:00:00Z",
        end="2023-02-02T00:00:00Z",
        interval="1m",
    )

    with pytest.raises(ValueError, match="no CSV rows matched"):
        list(feed.events())


@pytest.mark.parametrize("streaming", [None, False])
def test_exchange_rejects_empty_feed_before_strategy_init(tmp_path, streaming):
    start_ms = 1_672_531_200_000
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-01.csv",
        [_csv_row(start_ms, 100)],
    )

    class InitProbeStrategy(Strategy):
        def on_init(self):
            self.initialized = True

    strategy = InitProbeStrategy(
        strategy_id="empty-feed",
        broker=Broker(initial_cash=1000, fee_rate=0),
    )
    strategy.initialized = False
    exchange = Exchange()
    exchange.add_feed(
        CsvBarsFeed(
            tmp_path,
            symbols="BTCUSDT",
            start="2023-02-01T00:00:00Z",
            end="2023-02-02T00:00:00Z",
            interval="1m",
        )
    )
    exchange.add_strategy(strategy)

    with pytest.raises(ValueError, match="no CSV rows matched"):
        exchange.run(streaming=streaming)
    assert strategy.initialized is False


def test_csv_bars_feed_accepts_arrow_time_range(tmp_path):
    arrow = pytest.importorskip("arrow")
    start_ms = 1_672_531_200_000
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-01.csv",
        [_csv_row(start_ms, 100), _csv_row(start_ms + 60_000, 101)],
    )
    feed = CsvBarsFeed(
        tmp_path,
        symbols="BTCUSDT",
        start=arrow.get("2023-01-01T00:00:00+00:00"),
        end=arrow.get("2023-01-01T00:02:00+00:00"),
    )

    events = list(feed.events())
    assert len(events) == 2


class _StreamingStrategy(Strategy):
    def on_init(self):
        self.calls = []

    def on_bars(self, dt, bars):
        self.calls.append(
            (dt, list(bars), self.feed.after_first_yield, self.feed.after_second_yield)
        )


class _ProbeFeed:
    name = "probe"
    event_type = "bars"
    streaming = True

    def __init__(self):
        self.after_first_yield = False
        self.after_second_yield = False
        self.closed = False

    def _event(self, dt, close):
        return FeedEvent(
            event_type="bars",
            dt=dt,
            data={
                "BTCUSDT": {
                    "dt": dt,
                    "symbol": "BTCUSDT",
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": 1.0,
                }
            },
        )

    def events(self):
        first_dt = datetime(2024, 1, 1, tzinfo=UTC)
        yield self._event(first_dt, 100.0)
        self.after_first_yield = True
        yield self._event(first_dt + timedelta(minutes=1), 101.0)
        self.after_second_yield = True
        yield self._event(first_dt + timedelta(minutes=2), 102.0)

    def close(self):
        self.closed = True


def test_exchange_streaming_dispatches_before_source_is_exhausted():
    feed = _ProbeFeed()
    strategy = _StreamingStrategy(
        strategy_id="streaming",
        broker=Broker(initial_cash=1000, fee_rate=0),
    )
    strategy.feed = feed
    exchange = Exchange()
    exchange.add_feed(feed)
    exchange.add_strategy(strategy)

    exchange.run()

    # 为了确认一个 dt 已经结束，调度器最多向前读取一个事件；但不会读完整个源。
    assert strategy.calls[0][2] is True
    assert strategy.calls[0][3] is False
    assert strategy.calls[1][3] is True
    assert feed.closed is True


def test_streaming_run_ignores_canceled_order_from_closed_portfolio(tmp_path):
    start_ms = 1_672_531_200_000
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-01.csv",
        [_csv_row(start_ms, 100), _csv_row(start_ms + 60_000, 80)],
    )

    class ClosePendingPortfolioStrategy(Strategy):
        def on_init(self):
            self.step = 0
            self.pending = None

        def on_bars(self, dt, bars):
            if self.step == 0:
                self.broker.add_portfolio("alt", cash=300)
                self.pending = self.broker.submit_limit_order(
                    "BTCUSDT",
                    qty=1,
                    limit_price=90,
                    portfolio="alt",
                )
                self.broker.close_portfolio("alt")
            self.step += 1

    strategy = ClosePendingPortfolioStrategy(
        strategy_id="close-pending",
        broker=Broker(initial_cash=1000, fee_rate=0),
    )
    exchange = Exchange()
    exchange.add_feed(
        CsvBarsFeed(
            tmp_path,
            symbols="BTCUSDT",
            start="2023-01-01T00:00:00Z",
            end="2023-01-01T00:02:00Z",
        )
    )
    exchange.add_strategy(strategy)

    exchange.run()

    assert strategy.pending.status == "canceled"
    assert strategy.broker.get_portfolios() == ["main"]
    assert strategy.broker.get_position_size("BTCUSDT") == 0


def test_exchange_streaming_rejects_out_of_order_feed():
    class OutOfOrderFeed(_ProbeFeed):
        name = "out-of-order"

        def events(self):
            first_dt = datetime(2024, 1, 1, tzinfo=UTC)
            yield self._event(first_dt + timedelta(minutes=1), 101.0)
            yield self._event(first_dt, 100.0)

    exchange = Exchange()
    exchange.add_feed(OutOfOrderFeed())
    exchange.add_strategy(
        Strategy(strategy_id="streaming", broker=Broker(initial_cash=1000, fee_rate=0))
    )

    with pytest.raises(ValueError, match="not ordered"):
        exchange.run()


def test_streaming_feeds_with_same_dt_follow_event_type_order():
    dt = datetime(2024, 1, 1, tzinfo=UTC)

    class OneEventFeed:
        streaming = True

        def __init__(self, name, event_type, data, prices=None):
            self.name = name
            self.event_type = event_type
            self.data = data
            self.prices = prices

        def events(self):
            yield FeedEvent(
                event_type=self.event_type,
                dt=dt,
                data=self.data,
                prices=self.prices,
            )

    class CallbackOrderStrategy(Strategy):
        def on_init(self):
            self.calls = []

        def on_bars(self, event_dt, bars):
            self.calls.append("bars")

        def on_books(self, event_dt, books):
            self.calls.append("books")

        def on_trades(self, event_dt, trades):
            self.calls.append("trades")

        def on_news(self, event_dt, news):
            self.calls.append("news")

    exchange = Exchange()
    # 故意逆序注册，验证排序由事件类型契约而不是注册顺序决定。
    exchange.add_feed(OneEventFeed("news", "news", [{"headline": "n"}]))
    exchange.add_feed(
        OneEventFeed(
            "trades",
            "trades",
            {"BTCUSDT": [{"symbol": "BTCUSDT", "price": 101.0}]},
            {"BTCUSDT": 101.0},
        )
    )
    exchange.add_feed(
        OneEventFeed("books", "books", {"BTCUSDT": {"symbol": "BTCUSDT"}})
    )
    exchange.add_feed(
        OneEventFeed(
            "bars",
            "bars",
            {"BTCUSDT": {"symbol": "BTCUSDT", "close": 100.0}},
            {"BTCUSDT": 100.0},
        )
    )
    strategy = CallbackOrderStrategy(
        strategy_id="callback-order",
        broker=Broker(initial_cash=1000, fee_rate=0),
    )
    exchange.add_strategy(strategy)

    exchange.run()

    assert strategy.calls == ["bars", "books", "trades", "news"]


def _iosql_row(symbol, open_time, close):
    return {
        "symbol": symbol,
        "open_time": open_time,
        "open": close - 1,
        "high": close + 1,
        "low": close - 2,
        "close": close,
        "volume": 10,
        "close_time": open_time + 59_999,
        "volume_quote": 100,
        "num_trades": 42,
        "volume_base_buy": 5,
        "volume_quote_buy": 50,
        "ignored": "0",
    }


def _create_iosql_bars(uri, rows):
    iosql = pytest.importorskip("iosql")
    with iosql.Database(uri) as db:
        table = db.table(
            "kline_1m",
            pk=["symbol", "open_time"],
            time="open_time",
            symbol_column="symbol",
            columns={
                "symbol": "text",
                "open_time": "integer",
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
                "volume": "float",
                "close_time": "integer",
                "volume_quote": "float",
                "num_trades": "float",
                "volume_base_buy": "float",
                "volume_quote_buy": "float",
                "ignored": "text",
            },
            partition="duration(open_time,every=1day)",
            order_key="open_time",
        )
        if rows:
            table.write(rows)


def test_iosql_bars_feed_uses_ordered_streaming_query(tmp_path, monkeypatch):
    pytest.importorskip("iosql")
    from iosql.engines.sqlite.table import Table

    db_path = tmp_path / "kline.iosql"
    uri = f"sqlite://{db_path}"
    _create_iosql_bars(
        uri,
        [
            _iosql_row("BTCUSDT", 1_672_531_200_000 + index * 60_000, 100 + index)
            for index in range(3)
        ],
    )

    def must_not_select(*args, **kwargs):
        raise AssertionError("IosqlBarsFeed must use iter_rows(), not select()")

    monkeypatch.setattr(Table, "select", must_not_select)
    feed = IosqlBarsFeed(
        uri,
        interval="1m",
        symbols="BTCUSDT",
        start="2023-01-01T00:00:00Z",
        end="2023-01-01T00:02:00Z",
        batch_size=1,
    )

    events = list(feed.events())
    assert [event.data["BTCUSDT"]["close"] for event in events] == [100.0, 101.0]


def test_iosql_bars_feed_rejects_missing_table_with_clear_context(tmp_path):
    iosql = pytest.importorskip("iosql")
    uri = f"sqlite://{tmp_path / 'empty.iosql'}"
    with iosql.Database(uri):
        pass
    feed = IosqlBarsFeed(uri, interval="1h")

    with pytest.raises(ValueError, match="table 'kline_1h' not found.*interval='1h'"):
        list(feed.events())
    assert feed._db is None


def test_iosql_bars_feed_rejects_missing_requested_symbol(tmp_path):
    uri = f"sqlite://{tmp_path / 'kline.iosql'}"
    _create_iosql_bars(
        uri,
        [_iosql_row("BTCUSDT", 1_672_531_200_000, 100)],
    )
    feed = IosqlBarsFeed(
        uri,
        interval="1m",
        symbols=["BTCUSDT", "ETHUSDT"],
    )

    with pytest.raises(ValueError, match="ETHUSDT"):
        list(feed.events())
    assert feed._db is None


def test_iosql_bars_feed_rejects_range_without_rows(tmp_path):
    uri = f"sqlite://{tmp_path / 'kline.iosql'}"
    _create_iosql_bars(
        uri,
        [_iosql_row("BTCUSDT", 1_672_531_200_000, 100)],
    )
    feed = IosqlBarsFeed(
        uri,
        interval="1m",
        symbols="BTCUSDT",
        start="2023-02-01T00:00:00Z",
        end="2023-02-02T00:00:00Z",
    )

    with pytest.raises(ValueError, match="BTCUSDT"):
        list(feed.events())


def test_iosql_bars_feed_rejects_empty_table_without_symbol_filter(tmp_path):
    uri = f"sqlite://{tmp_path / 'empty-kline.iosql'}"
    _create_iosql_bars(uri, [])
    feed = IosqlBarsFeed(uri, interval="1m")

    with pytest.raises(ValueError, match="no iosql rows matched"):
        list(feed.events())


def test_iosql_bars_feed_wraps_invalid_table_contract(tmp_path):
    iosql = pytest.importorskip("iosql")
    uri = f"sqlite://{tmp_path / 'broken.iosql'}"
    with iosql.Database(uri) as db:
        table = db.table("broken", pk=["id"], columns={"id": "integer"})
        table.write([{"id": 1}])
    feed = IosqlBarsFeed(uri, interval="1m", table="broken")

    with pytest.raises(
        ValueError,
        match="failed to query iosql table='broken'.*interval='1m'.*check uri",
    ):
        list(feed.events())


@pytest.mark.parametrize("batch_size", [None, 1.5, True, 0, -1])
def test_iosql_bars_feed_rejects_invalid_batch_size(batch_size):
    with pytest.raises(ValueError, match="batch_size must be a positive integer"):
        IosqlBarsFeed("sqlite:///tmp/data.iosql", interval="1m", batch_size=batch_size)


class _EquityRecorder(Strategy):
    """记录回调序列与逐 bar 权益，用于流式/物化等价性比较。"""

    def on_init(self):
        self.calls = []
        self.equities = []

    def on_bars(self, dt, bars):
        self.calls.append((dt, tuple(bars), tuple(bars[s]["close"] for s in bars)))
        if "BTCUSDT" in bars:
            price = bars["BTCUSDT"]["close"]
            if self.broker.get_position_size("BTCUSDT") == 0:
                self.broker.order_target_percent("BTCUSDT", 0.5, price=price)
        self.equities.append(self.broker.get_total_equity())


def _build_bars_rows():
    start_ms = 1_672_531_200_000
    rows = []
    for index in range(6):
        dt_ms = start_ms + index * 60_000
        close = 100 + index
        for symbol, base in (("BTCUSDT", 0), ("ETHUSDT", 1000)):
            rows.append(
                {
                    "dt": datetime.fromtimestamp(dt_ms / 1000, tz=UTC),
                    "symbol": symbol,
                    "open": close - 1 + base,
                    "high": close + 1 + base,
                    "low": close - 2 + base,
                    "close": close + base,
                    "volume": 10.0,
                }
            )
    return rows


def _write_bars_csv(root: Path, rows):
    by_month = {}
    for row in rows:
        month = row["dt"].strftime("%Y-%m")
        by_month.setdefault((row["symbol"], month), []).append(row)
    for (symbol, month), month_rows in by_month.items():
        lines = ["open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore"]
        for row in month_rows:
            open_time = int(row["dt"].timestamp() * 1000)
            close = row["close"]
            lines.append(
                f"{open_time},{row['open']},{row['high']},{row['low']},{close},{row['volume']},"
                f"{open_time + 59_999},100,42,5,50,0"
            )
        (root / f"{symbol}-1m-{month}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_strategy(strategy_id):
    strategy = _EquityRecorder(
        strategy_id=strategy_id,
        broker=Broker(initial_cash=10_000, fee_rate=0.001),
    )
    return strategy


def _strategy_summary(strategy):
    return {
        "calls": strategy.calls,
        "equities": [round(float(e), 10) for e in strategy.equities],
        "final_position": strategy.broker.get_position_size("BTCUSDT"),
        "final_equity": round(float(strategy.broker.get_total_equity()), 10),
    }


def test_streaming_matches_materialized_set_bars(tmp_path):
    rows = _build_bars_rows()

    materialized_strategy = _make_strategy("materialized")
    exchange = Exchange()
    exchange.set_bars(rows)
    exchange.add_strategy(materialized_strategy)
    exchange.run(streaming=False)

    _write_bars_csv(tmp_path, rows)
    streaming_strategy = _make_strategy("streaming")
    exchange = Exchange()
    exchange.add_feed(
        CsvBarsFeed(
            tmp_path,
            symbols=["BTCUSDT", "ETHUSDT"],
            start="2023-01-01T00:00:00Z",
            end="2023-01-01T00:06:00Z",
        )
    )
    exchange.add_strategy(streaming_strategy)
    exchange.run()

    assert _strategy_summary(streaming_strategy) == _strategy_summary(materialized_strategy)


def test_exchange_streaming_repeated_runs_are_identical(tmp_path):
    _write_bars_csv(tmp_path, _build_bars_rows())
    exchange = Exchange()
    exchange.add_feed(
        CsvBarsFeed(
            tmp_path,
            symbols=["BTCUSDT", "ETHUSDT"],
            start="2023-01-01T00:00:00Z",
            end="2023-01-01T00:06:00Z",
        )
    )
    first_strategy = _make_strategy("run-1")
    exchange.add_strategy(first_strategy)
    exchange.run()

    second_strategy = _make_strategy("run-2")
    exchange.add_strategy(second_strategy)
    exchange.run()

    assert _strategy_summary(first_strategy) == _strategy_summary(second_strategy)


def test_exchange_run_streaming_true_requires_streaming_feeds():
    dt = datetime(2024, 1, 1, tzinfo=UTC)
    exchange = Exchange()
    exchange.set_bars([{"dt": dt, "symbol": "BTCUSDT", "close": 100.0}])
    exchange.add_strategy(
        Strategy(strategy_id="s", broker=Broker(initial_cash=1000, fee_rate=0))
    )

    with pytest.raises(ValueError, match="streaming=True requires"):
        exchange.run(streaming=True)


def test_exchange_run_streaming_false_uses_materialized_path(tmp_path):
    _write_bars_csv(tmp_path, _build_bars_rows())
    feed = CsvBarsFeed(
        tmp_path,
        symbols=["BTCUSDT", "ETHUSDT"],
        start="2023-01-01T00:00:00Z",
        end="2023-01-01T00:06:00Z",
    )
    exchange = Exchange()
    exchange.add_feed(feed)
    strategy = _make_strategy("materialized-force")
    exchange.add_strategy(strategy)
    exchange.run(streaming=False)

    assert len(strategy.calls) == 6
    # 物化路径复用同一 feed：on_init 会重置记录，第二次 run 重新记录且内容一致
    first_run_calls = list(strategy.calls)
    exchange.run(streaming=False)
    assert len(strategy.calls) == 6
    assert strategy.calls == first_run_calls
