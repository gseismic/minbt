"""手工构造 CSV / 真实 iosql 数据库，验证分钟缺口诊断。"""

import csv
import warnings

import pytest

from minbt import Exchange, Strategy
from minbt.plugins.binance.feed import KlineCsvFeed, KlineIosqlFeed
from minbt.plugins.binance._kline import ms_to_datetime


START_MS = 1_672_531_200_000


@pytest.fixture(params=["csv", "iosql"])
def make_feed(tmp_path, request):
    def make(minutes_by_symbol, *, end_ms=None, interval="1m"):
        duration = 60_000 if interval == "1m" else 300_000
        rows = sorted(
            [
                {
                    "symbol": symbol,
                    "open_time": START_MS + minute * 60_000,
                    "close_time": START_MS + minute * 60_000 + duration - 1,
                    "close": 100.0,
                }
                for symbol, minutes in minutes_by_symbol.items()
                for minute in minutes
            ],
            key=lambda row: (row["open_time"], row["symbol"]),
        )
        kwargs = {
            "interval": interval,
            "start": ms_to_datetime(START_MS),
            "end": ms_to_datetime(end_ms) if end_ms is not None else None,
        }
        if request.param == "csv":
            for symbol in minutes_by_symbol:
                path = tmp_path / f"{symbol}-{interval}-2023-01.csv"
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    for row in rows:
                        if row["symbol"] == symbol:
                            writer.writerow([
                                row["open_time"], 100, 101, 99, row["close"], 1,
                                row["close_time"], 100, 1, 0, 0, 0,
                            ])
            return KlineCsvFeed(tmp_path, **kwargs)

        iosql = pytest.importorskip("iosql")
        uri = f"sqlite://{tmp_path / 'bars.iosql'}"
        with iosql.Database(uri) as db:
            table = db.table(
                f"kline_{interval}",
                pk=["symbol", "open_time"],
                time="open_time",
                symbol_column="symbol",
                columns={
                    "symbol": "text", "open_time": "integer",
                    "close_time": "integer", "close": "float",
                },
                partition="duration(open_time,every=1day)",
                order_key="open_time",
            )
            result = table.write(rows)
            assert result.rows_written == len(rows)
        # 很小的读取批次，确保检查能跨数据库缓冲边界。
        return KlineIosqlFeed(uri, batch_size=1, **kwargs)

    return make


def test_continuous_and_late_listed_symbols_do_not_warn(make_feed):
    feed = make_feed({"BTCUSDT": [0, 1, 2, 3], "ETHUSDT": [2, 3]},
                     end_ms=START_MS + 4 * 60_000)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        events = list(feed.events())
    assert caught == []
    assert len(events) == 6


@pytest.mark.parametrize("end_ms", [None, START_MS + 5 * 60_000])
def test_only_first_gap_per_symbol_is_reported(make_feed, end_ms):
    feed = make_feed({"BTCUSDT": [0, 2, 4], "ETHUSDT": [0, 1, 2, 3, 4]}, end_ms=end_ms)
    with pytest.warns(RuntimeWarning, match="BTCUSDT 1m Kline missing") as caught:
        events = list(feed.events())
    assert len(caught) == 1
    message = str(caught[0].message)
    assert "first missing open_time=2023-01-01T00:01:00+00:00" in message
    assert "last seen open_time=2023-01-01T00:00:00+00:00" in message
    assert feed.name in message
    assert "delisting" in message
    assert len(events) == 8


def test_permanent_disappearance_without_end_warns(make_feed):
    feed = make_feed({"BTCUSDT": [0, 1, 2, 3], "ETHUSDT": [0]})
    with pytest.warns(RuntimeWarning, match="ETHUSDT 1m Kline missing") as caught:
        assert len(list(feed.events())) == 5
    assert len(caught) == 1


def test_whole_missing_minute_warns_for_each_seen_symbol(make_feed):
    feed = make_feed({"BTCUSDT": [0, 2], "ETHUSDT": [0, 2]})
    with pytest.warns(RuntimeWarning) as caught:
        assert len(list(feed.events())) == 4
    assert len(caught) == 2
    assert all("first missing open_time=2023-01-01T00:01:00+00:00" in str(w.message)
               for w in caught)
    for symbol in ("BTCUSDT", "ETHUSDT"):
        assert sum(f": {symbol} 1m Kline missing" in str(w.message) for w in caught) == 1


def test_trailing_gap_is_checked_against_explicit_end(make_feed):
    feed = make_feed({"BTCUSDT": [0, 1]}, end_ms=START_MS + 4 * 60_000)
    with pytest.warns(RuntimeWarning, match="first missing open_time=2023-01-01T00:02:00") as caught:
        assert len(list(feed.events())) == 2
    assert len(caught) == 1


@pytest.mark.parametrize("end_ms", [None, START_MS + 2 * 60_000])
def test_no_warning_beyond_data_or_exclusive_end(make_feed, end_ms):
    feed = make_feed({"BTCUSDT": [0, 1]}, end_ms=end_ms)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert len(list(feed.events())) == 2
    assert caught == []


def test_non_aligned_end_still_expects_last_included_open_time(make_feed):
    feed = make_feed({"BTCUSDT": [0, 1]}, end_ms=START_MS + 2 * 60_000 + 1)
    with pytest.warns(RuntimeWarning, match="first missing open_time=2023-01-01T00:02:00"):
        assert len(list(feed.events())) == 2


def test_other_intervals_do_not_use_minute_continuity(make_feed):
    feed = make_feed({"BTCUSDT": [0, 10]}, interval="5m", end_ms=START_MS + 15 * 60_000)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert len(list(feed.events())) == 2
    assert caught == []


def test_warning_state_resets_on_replay(make_feed):
    feed = make_feed({"BTCUSDT": [0, 2]})
    with pytest.warns(RuntimeWarning) as caught:
        assert len(list(feed.events())) == 2
        assert len(list(feed.events())) == 2
    assert len(caught) == 2


def test_early_close_does_not_report_unread_tail(make_feed):
    feed = make_feed({"BTCUSDT": [0, 1]}, end_ms=START_MS + 4 * 60_000)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        events = iter(feed.events())
        next(events)
        events.close()
    assert caught == []
    if isinstance(feed, KlineIosqlFeed):
        assert feed._db is None


@pytest.mark.parametrize("load_mode", ["preload", "incremental"])
def test_backtest_continues_and_warns_before_missing_symbol_callback(make_feed, load_mode):
    feed = make_feed({"BTCUSDT": [0, 2], "ETHUSDT": [0, 1, 2]},
                     end_ms=START_MS + 3 * 60_000)

    class Probe(Strategy):
        def on_bars(self, dt, bars):
            seen.append(set(bars))
            if set(bars) == {"ETHUSDT"}:
                assert len(caught) == 1

    seen = []
    exchange = Exchange()
    exchange.add_feed(feed)
    exchange.add_strategy(Probe("gap-probe"))
    with pytest.warns(RuntimeWarning, match="BTCUSDT 1m Kline missing") as caught:
        exchange.run(load_mode=load_mode)
    assert len(caught) == 1
    assert seen == [{"BTCUSDT", "ETHUSDT"}, {"ETHUSDT"}, {"BTCUSDT", "ETHUSDT"}]
