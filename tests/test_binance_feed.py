from datetime import datetime, timezone

import pytest

from minbt.data import binance


def _row(open_time, *, close_time=None):
    if close_time is None:
        close_time = open_time + 59_999
    return {
        "open_time": open_time,
        "open": 100,
        "high": 101,
        "low": 99,
        "close": 100,
        "volume": 1,
        "close_time": close_time,
    }


class _Client:
    def __init__(self, rows):
        self.rows = rows

    def fetch_klines(self, *args, **kwargs):
        return self.rows


def _feed(tmp_path, start_ms, end_ms, *, closed_only=True, cache_only=False):
    return binance.BinanceKlineFeed(
        "BTCUSDT",
        "1m",
        datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc),
        datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc),
        tmp_path,
        closed_only=closed_only,
        cache_only=cache_only,
    )


def test_binance_empty_response_does_not_record_coverage(tmp_path):
    start_ms = 1_672_531_200_000
    feed = _feed(tmp_path, start_ms, start_ms + 120_000)
    feed._client = _Client([])

    with pytest.raises(RuntimeError, match="no usable klines"):
        feed.prepare()

    assert feed._coverage_intervals("BTCUSDT") == []


def test_closed_only_does_not_accept_rows_without_close_time(tmp_path):
    start_ms = 1_672_531_200_000
    row = _row(start_ms)
    row["close_time"] = None
    feed = _feed(tmp_path, start_ms, start_ms + 60_000)
    feed._client = _Client([row])

    with pytest.raises(RuntimeError, match="no usable klines"):
        feed.prepare()

    assert feed._coverage_intervals("BTCUSDT") == []


def test_binance_incomplete_response_does_not_record_coverage(tmp_path):
    start_ms = 1_672_531_200_000
    feed = _feed(tmp_path, start_ms, start_ms + 180_000)
    feed._client = _Client([_row(start_ms), _row(start_ms + 120_000)])

    with pytest.raises(RuntimeError, match="incomplete kline range"):
        feed.prepare()

    assert feed._coverage_intervals("BTCUSDT") == []


def test_closed_only_filters_unclosed_rows_from_existing_cache(tmp_path, monkeypatch):
    interval_ms = 60_000
    now_ms = 1_750_000_030_000
    current_open = (now_ms // interval_ms) * interval_ms
    monkeypatch.setattr(binance, "_current_open_time_ms", lambda _now, _interval: current_open)
    start_ms = current_open - 3 * interval_ms
    end_ms = current_open + interval_ms

    inclusive_feed = _feed(tmp_path, start_ms, end_ms, closed_only=False)
    inclusive_feed._client = _Client(
        [_row(start_ms + offset) for offset in (0, 60_000, 120_000)]
        + [_row(current_open, close_time=10**15)]
    )
    inclusive_feed.prepare()
    assert len(inclusive_feed._rows) == 4

    closed_feed = _feed(tmp_path, start_ms, end_ms, closed_only=True)
    closed_feed._client = _Client([])
    closed_feed.prepare()

    assert [row["dt_ms"] for row in closed_feed._rows] == [
        start_ms,
        start_ms + interval_ms,
        start_ms + 2 * interval_ms,
    ]


def test_closed_only_redownloads_a_candle_cached_before_close(tmp_path, monkeypatch):
    interval_ms = 60_000
    start_ms = (1_700_000_000_000 // interval_ms) * interval_ms
    now_ms = [start_ms + 30_000]
    monkeypatch.setattr(binance.time, "time", lambda: now_ms[0] / 1000)
    end_ms = start_ms + interval_ms
    row = _row(start_ms)

    open_feed = _feed(tmp_path, start_ms, end_ms, closed_only=False)
    open_feed._client = _Client([row])
    open_feed.prepare()
    assert open_feed._rows[0]["downloaded_at_ms"] < row["close_time"]

    now_ms[0] = start_ms + 120_000
    closed_feed = _feed(tmp_path, start_ms, end_ms, closed_only=True)
    closed_feed._client = _Client([row])
    closed_feed.prepare()

    assert len(closed_feed._rows) == 1
    assert closed_feed._rows[0]["downloaded_at_ms"] > row["close_time"]


def test_old_binance_cache_schema_invalidates_coverage(tmp_path):
    start_ms = 1_672_531_200_000
    feed = _feed(tmp_path, start_ms, start_ms + 60_000)
    with feed._connect() as conn:
        conn.executescript(
            """
            CREATE TABLE bars (
                source TEXT NOT NULL, market TEXT NOT NULL, symbol TEXT NOT NULL,
                interval TEXT NOT NULL, dt_ms INTEGER NOT NULL, open REAL NOT NULL,
                high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
                volume REAL NOT NULL, close_time INTEGER, volume_quote REAL,
                num_trades INTEGER, volume_base_buy REAL, volume_quote_buy REAL,
                PRIMARY KEY (source, market, symbol, interval, dt_ms)
            );
            CREATE TABLE bar_coverage (
                source TEXT NOT NULL, market TEXT NOT NULL, symbol TEXT NOT NULL,
                interval TEXT NOT NULL, start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL,
                PRIMARY KEY (source, market, symbol, interval, start_ms, end_ms)
            );
            """
        )
        conn.execute(
            "INSERT INTO bar_coverage VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("binance", "futures", "BTCUSDT", "1m", start_ms, start_ms + 60_000, 0),
        )

    feed._ensure_schema()

    columns = {row["name"] for row in feed._connect().execute("PRAGMA table_info(bars)")}
    assert "downloaded_at_ms" in columns
    assert feed._coverage_intervals("BTCUSDT") == []


def test_binance_cache_with_empty_coverage_is_rejected(tmp_path):
    start_ms = 1_672_531_200_000
    end_ms = start_ms + 60_000
    feed = _feed(tmp_path, start_ms, end_ms, cache_only=False)
    feed._ensure_schema()
    with feed._connect() as conn:
        feed._replace_coverage(conn, "BTCUSDT", start_ms, end_ms)

    cache_feed = _feed(tmp_path, start_ms, end_ms, cache_only=True)

    with pytest.raises(RuntimeError, match="no usable klines"):
        cache_feed.prepare()
