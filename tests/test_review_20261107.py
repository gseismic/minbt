"""覆盖全量代码评审中发现的交易边界与本地数据读取问题。"""

import csv
from datetime import date
from pathlib import Path
import subprocess
import sys

import pytest

from minbt import Broker, Exchange, Market, Strategy, markets
from minbt.broker.struct import Position
from minbt.plugins.binance.feed import KlineCsvFeed, KlineIosqlFeed
from minbt.plugins.binance.feed import csv as csv_feed


@pytest.mark.parametrize("explicit_price", [False, True])
def test_other_market_midnight_cannot_make_stale_stock_quote_a_daily_bar(explicit_price):
    """其他市场的午夜行情不能使旧 A 股报价绕过盘前交易限制。"""
    class Buyer(Strategy):
        def on_bars(self, dt, bars):
            if "BTC" in bars:
                options = {"price": 10, "price_dt": dt} if explicit_price else {}
                self.order = self.broker.submit_market_order("STOCK", 100, **options)

    broker = Broker(10000)
    broker.add_market("stock", markets.A_STOCK, ["STOCK"])
    exchange = Exchange()
    exchange.set_bars([
        {"dt": "2026-01-02T06:55:00Z", "symbol": "STOCK", "close": 10},
        {"dt": "2026-01-05T00:00:00Z", "symbol": "BTC", "close": 100},
    ])
    strategy = Buyer("buyer", broker)
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.order.status == "rejected"
    assert "not in trading time" in strategy.order.reason
    assert broker.get_position_size("STOCK") == 0


def test_current_stock_daily_bar_still_allows_midnight_trade():
    """标的自身在当前批次有日线时，既有日线策略仍可交易。"""
    class Buyer(Strategy):
        def on_bars(self, dt, bars):
            if "STOCK" in bars:
                self.order = self.broker.submit_market_order("STOCK", 100)

    broker = Broker(10000, market=markets.A_STOCK)
    exchange = Exchange()
    exchange.set_bars([{"dt": "2026-01-05", "symbol": "STOCK", "close": 10}])
    strategy = Buyer("buyer", broker)
    exchange.add_strategy(strategy)
    exchange.run()
    assert strategy.order.status == "filled"


def test_t1_requires_dated_trade_and_keeps_unknown_locked_lots():
    """缺少交易日时拒绝 T+1 交易，既有未知日期锁仓不能自动解锁。"""
    broker = Broker(1000, market=Market(t_plus=1))
    order = broker.submit_market_order("X", 1, price=10)
    assert order.status == "rejected"
    assert "trading date" in order.reason
    assert broker.get_position_size("X") == 0

    position = Position("X", size=1)
    position.lock_size(1, None)
    position.unlock_before(date(2026, 1, 5))
    assert position.locked_size == 1
    assert position.available_size == 0


def _write_bar_file(root: Path, symbol: str, month: str, times):
    with (root / f"{symbol}-5m-{month}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for timestamp in times:
            writer.writerow([timestamp, 100, 101, 99, 100, 1, timestamp + 299999, 100, 1, 1, 1, 0])


def test_csv_wildcard_ignores_symbols_without_rows_in_requested_window(tmp_path):
    """目录中区间外的币种不应使全标的回放失败。"""
    jan, feb = 1672531200000, 1675209600000
    _write_bar_file(tmp_path, "BTC", "2023-01", [jan])
    _write_bar_file(tmp_path, "NEW", "2023-02", [feb])
    feed = KlineCsvFeed(tmp_path, "*", "2023-01-01", "2023-02-01", interval="5m")
    assert [event.symbol for event in feed.events()] == ["BTC"]
    assert feed.symbols == ["BTC"]


def test_csv_wildcard_allows_symbol_lifecycle_edges_but_detects_internal_gap(tmp_path):
    """通配符允许上市前和停止后的空月份，仍检查中间缺失文件。"""
    jan, feb, mar = 1672531200000, 1675209600000, 1677628800000
    _write_bar_file(tmp_path, "BTC", "2023-01", [jan])
    _write_bar_file(tmp_path, "BTC", "2023-02", [feb])
    _write_bar_file(tmp_path, "BTC", "2023-03", [mar])
    _write_bar_file(tmp_path, "NEW", "2023-02", [feb])
    _write_bar_file(tmp_path, "OLD", "2023-01", [jan])
    feed = KlineCsvFeed(tmp_path, "*", "2023-01-01", "2023-04-01", interval="5m")
    assert [(event.symbol, event.data["open_time"]) for event in feed.events()] == [
        ("BTC", jan), ("OLD", jan), ("BTC", feb), ("NEW", feb), ("BTC", mar),
    ]

    _write_bar_file(tmp_path, "GAP", "2023-01", [jan])
    _write_bar_file(tmp_path, "GAP", "2023-03", [mar])
    with pytest.raises(FileNotFoundError, match="GAP@2023-02"):
        list(KlineCsvFeed(tmp_path, "*", "2023-01-01", "2023-04-01", interval="5m").events())


def test_csv_wildcard_ignores_boundary_month_files_with_only_out_of_range_rows(tmp_path):
    """边界月文件存在但没有匹配行时，不能据此要求币种此前月份完整。"""
    jan, mar = 1672531200000, 1677628800000
    _write_bar_file(tmp_path, "NEW", "2023-01", [jan])
    _write_bar_file(tmp_path, "NEW", "2023-03", [mar])
    feed = KlineCsvFeed(tmp_path, "*", "2023-01-15", "2023-04-01", interval="5m")
    assert [event.data["open_time"] for event in feed.events()] == [mar]


def test_csv_buffered_merge_preserves_order_and_checks_chunk_boundaries(tmp_path, monkeypatch):
    """跨块归并保持时间顺序，逆序数据仍会被发现。"""
    start = 1672531200000
    _write_bar_file(tmp_path, "A", "2023-01", [start, start + 600000, start + 1200000])
    _write_bar_file(tmp_path, "B", "2023-01", [start + 300000, start + 900000, start + 1500000])
    monkeypatch.setattr(csv_feed, "_CSV_READ_BATCH_SIZE", 2)
    events = list(KlineCsvFeed(tmp_path, "*", interval="5m").events())
    assert [event.symbol for event in events] == ["A", "B", "A", "B", "A", "B"]

    _write_bar_file(tmp_path, "A", "2023-01", [start, start + 600000, start + 300000])
    with pytest.raises(ValueError, match="not ordered"):
        list(KlineCsvFeed(tmp_path, "*", interval="5m").events())


def test_csv_buffered_reader_delivers_valid_rows_before_later_error(tmp_path):
    """块内后续坏行不能阻止之前的合法行情按需交付。"""
    start = 1672531200000
    _write_bar_file(tmp_path, "BTC", "2023-01", [start, start + 300000])
    with (tmp_path / "BTC-5m-2023-01.csv").open("a", encoding="utf-8") as handle:
        handle.write("bad,row\n")

    events = iter(KlineCsvFeed(tmp_path, "*", interval="5m").events())
    assert next(events).data["open_time"] == start
    assert next(events).data["open_time"] == start + 300000
    with pytest.raises(ValueError, match="fewer than 12 columns"):
        next(events)


def test_csv_wildcard_does_not_hold_one_descriptor_per_symbol(tmp_path):
    """在较低描述符上限下读取比上限更多的币种。"""
    pytest.importorskip("resource")
    for index in range(40):
        _write_bar_file(tmp_path, f"S{index:03d}", "2023-01", [1672531200000])
    code = """
import resource
import sys
from minbt.plugins.binance.feed import KlineCsvFeed
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
limit = 32 if hard == resource.RLIM_INFINITY else min(32, hard)
resource.setrlimit(resource.RLIMIT_NOFILE, (limit, hard))
assert len(list(KlineCsvFeed(sys.argv[1], '*', interval='5m').events())) == 40
"""
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_iosql_kline_normalizes_quote_buy_volume_text(tmp_path):
    """iosql 读取文本数值时，主动买入额与其他价量字段均为 float。"""
    iosql = pytest.importorskip("iosql")
    uri = f"iosql://{tmp_path / 'kline.iosql'}"
    with iosql.Database.create(uri, engine="sqlite") as db:
        table = db.table(
            "kline_5m", pk=["symbol", "open_time"], time="open_time", symbol_column="symbol",
            columns={"symbol": "text", "open_time": "integer", "close_time": "integer",
                     "close": "text", "volume_quote_buy": "text"},
            partition="duration(open_time,every=1day)", order_key="open_time",
        )
        table.write([{"symbol": "BTC", "open_time": 1672531200000,
                      "close_time": 1672531499999, "close": "1.5", "volume_quote_buy": "9.8"}])

    event, = list(KlineIosqlFeed(uri, interval="5m").events())
    assert event.data["close"] == 1.5
    assert event.data["volume_quote_buy"] == 9.8
    assert isinstance(event.data["volume_quote_buy"], float)
