from pathlib import Path

import pytest

from minbt import Bar, Broker, Exchange, Strategy
from minbt.data import BinanceKlineCsvFeed, BinanceKlineIosqlFeed


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


def test_binance_kline_csv_feed_yields_individual_bars(tmp_path):
    start_ms = 1_672_531_200_000
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-01.csv",
        [_csv_row(start_ms, 100), _csv_row(start_ms + 60_000, 101)],
    )
    _write_csv(
        tmp_path / "ETHUSDT-1m-2023-01.csv",
        [_csv_row(start_ms, 200)],
        header=False,
    )

    feed = BinanceKlineCsvFeed(
        tmp_path,
        symbols=["BTCUSDT", "ETHUSDT"],
        start="2023-01-01T00:00:00Z",
        end="2023-01-01T00:02:00Z",
    )
    events = list(feed.events())

    assert all(isinstance(event, Bar) for event in events)
    assert [(event.symbol, event.data["close"]) for event in events] == [
        ("BTCUSDT", 100.0),
        ("ETHUSDT", 200.0),
        ("BTCUSDT", 101.0),
    ]
    assert all(event.kind == "kline" for event in events)


def test_binance_kline_csv_feed_rejects_out_of_order_rows(tmp_path):
    start_ms = 1_672_531_200_000
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-01.csv",
        [_csv_row(start_ms + 60_000, 101), _csv_row(start_ms, 100)],
    )
    with pytest.raises(ValueError, match="not ordered"):
        list(BinanceKlineCsvFeed(tmp_path, symbols="BTCUSDT").events())


def test_binance_kline_csv_feed_rejects_missing_months(tmp_path):
    start_ms = 1_672_531_200_000
    _write_csv(tmp_path / "BTCUSDT-1m-2023-01.csv", [_csv_row(start_ms, 100)])
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-03.csv",
        [_csv_row(start_ms + 86_400_000 * 59, 300)],
    )
    feed = BinanceKlineCsvFeed(
        tmp_path,
        symbols="BTCUSDT",
        start="2023-01-01T00:00:00Z",
        end="2023-04-01T00:00:00Z",
    )
    with pytest.raises(FileNotFoundError, match="BTCUSDT@2023-02"):
        list(feed.events())


def test_binance_kline_csv_feed_rejects_missing_requested_symbol(tmp_path):
    start_ms = 1_672_531_200_000
    _write_csv(tmp_path / "BTCUSDT-1m-2023-01.csv", [_csv_row(start_ms, 100)])
    feed = BinanceKlineCsvFeed(tmp_path, symbols=["BTCUSDT", "ETHUSDT"], interval="1m")
    with pytest.raises(FileNotFoundError, match="ETHUSDT"):
        list(feed.events())


def test_binance_kline_csv_infers_unbounded_months_per_symbol(tmp_path):
    jan_ms = 1_672_531_200_000
    mar_ms = jan_ms + 86_400_000 * 59
    _write_csv(tmp_path / "BTCUSDT-1m-2023-01.csv", [_csv_row(jan_ms, 100)])
    _write_csv(tmp_path / "ETHUSDT-1m-2023-03.csv", [_csv_row(mar_ms, 200)])

    feed = BinanceKlineCsvFeed(tmp_path, symbols=["BTCUSDT", "ETHUSDT"])

    assert [(event.symbol, event.data["close"]) for event in feed.events()] == [
        ("BTCUSDT", 100.0),
        ("ETHUSDT", 200.0),
    ]


def test_exchange_consumes_binance_kline_csv_feed_in_incremental_mode(tmp_path):
    start_ms = 1_672_531_200_000
    _write_csv(
        tmp_path / "BTCUSDT-1m-2023-01.csv",
        [_csv_row(start_ms, 100), _csv_row(start_ms + 60_000, 101)],
    )

    class Probe(Strategy):
        def on_init(self):
            self.prices = []

        def on_bars(self, dt, bars):
            self.prices.append(bars["BTCUSDT"]["close"])

    exchange = Exchange()
    exchange.add_feed(
        BinanceKlineCsvFeed(
            tmp_path,
            symbols="BTCUSDT",
            start="2023-01-01T00:00:00Z",
            end="2023-01-01T00:02:00Z",
        )
    )
    strategy = Probe("csv", Broker(initial_cash=1000))
    exchange.add_strategy(strategy)

    exchange.run(load_mode="incremental")

    assert strategy.prices == [100.0, 101.0]


def test_binance_kline_iosql_feed_declares_incremental_capability():
    feed = BinanceKlineIosqlFeed("sqlite:///tmp/example.iosql", interval="1m")
    assert feed.supports_incremental is True
    assert feed.supports_preload is True
    assert feed.ordered is True
    assert feed.replayable is True


def test_binance_kline_iosql_feed_reads_rows_as_bars(tmp_path):
    iosql = pytest.importorskip("iosql")
    uri = f"sqlite://{tmp_path / 'bars.iosql'}"
    rows = [
        {
            "symbol": "BTCUSDT",
            "open_time": 1_672_531_200_000,
            "open": 99.0,
            "high": 101.0,
            "low": 98.0,
            "close": 100.0,
            "volume": 10.0,
            "close_time": 1_672_531_259_999,
            "volume_quote": 1_000.0,
            "num_trades": 42,
            "volume_base_buy": 5.0,
            "volume_quote_buy": 500.0,
        },
        {
            "symbol": "BTCUSDT",
            "open_time": 1_672_531_260_000,
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 11.0,
            "close_time": 1_672_531_319_999,
            "volume_quote": 1_111.0,
            "num_trades": 43,
            "volume_base_buy": 5.5,
            "volume_quote_buy": 555.5,
        },
    ]
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
                "num_trades": "integer",
                "volume_base_buy": "float",
                "volume_quote_buy": "float",
            },
            partition="duration(open_time,every=1day)",
            order_key="open_time",
        )
        table.write(rows)

    feed = BinanceKlineIosqlFeed(
        uri,
        interval="1m",
        symbols="BTCUSDT",
        start="2023-01-01T00:00:00Z",
        end="2023-01-01T00:02:00Z",
    )

    events = list(feed.events())

    assert [(event.symbol, event.kind, event.data["close"]) for event in events] == [
        ("BTCUSDT", "kline", 100.0),
        ("BTCUSDT", "kline", 101.0),
    ]
