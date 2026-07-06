from collections import OrderedDict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Iterable, List
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from .feed import FeedEvent


SOURCE = "binance"
DEFAULT_DB_NAME = "minbt-data.sqlite3"
SUPPORTED_MARKET = "futures"
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_DELAY = 0.5
FUTURES_API_BASE = "https://fapi.binance.com"


class BinanceKlineClient:
    """内部下载适配层，封装 crypto_api 以便后续替换和测试。"""

    def list_symbols(self) -> List[str]:
        try:
            from crypto_api.binance.api import futures_all_symbols

            return [symbol.upper() for symbol in futures_all_symbols()]
        except ImportError:
            data = _http_get_json(f"{FUTURES_API_BASE}/fapi/v1/exchangeInfo", {})
            return [
                item["symbol"].upper()
                for item in data.get("symbols", [])
                if item.get("status") == "TRADING"
            ]

    def fetch_klines(
        self,
        symbol: str,
        period: str,
        start_dt: Any,
        end_dt: Any,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        delay: float = DEFAULT_DELAY,
    ) -> List[dict]:
        try:
            from crypto_api.binance.api import get_future_klines

            return get_future_klines(
                symbol.upper(),
                period,
                start_dt,
                end_dt,
                chunk_size=chunk_size,
                delay=delay,
                to_dict=True,
            )
        except ImportError:
            return _fetch_futures_klines_http(symbol, period, start_dt, end_dt, chunk_size, delay)

    def fetch_recent_klines(self, symbol: str, period: str, limit: int) -> List[list]:
        try:
            from crypto_api.binance import BnFutureAPI

            api = BnFutureAPI()
            return api.futures_klines(symbol=symbol.upper(), interval=period, limit=limit)
        except ImportError:
            return _http_get_json(
                f"{FUTURES_API_BASE}/fapi/v1/klines",
                {"symbol": symbol.upper(), "interval": period, "limit": int(limit)},
            )

    def fetch_raw_klines(
        self,
        symbol: str,
        period: str,
        start_time: int,
        end_time: int,
        limit: int = 5,
    ) -> List[list]:
        try:
            from crypto_api.binance import BnFutureAPI

            api = BnFutureAPI()
            return api.futures_klines(
                symbol=symbol.upper(),
                interval=period,
                startTime=start_time,
                endTime=end_time,
                limit=limit,
            )
        except ImportError:
            return _http_get_json(
                f"{FUTURES_API_BASE}/fapi/v1/klines",
                {
                    "symbol": symbol.upper(),
                    "interval": period,
                    "startTime": int(start_time),
                    "endTime": int(end_time),
                    "limit": int(limit),
                },
            )


class BarsReplayFeed:
    event_type = "bars"

    def __init__(
        self,
        symbols,
        interval,
        start,
        end,
        cache_dir,
        *,
        market="futures",
        name=None,
        refresh=False,
        cache_only=False,
        closed_only=True,
    ):
        self.symbols = self._normalize_symbols(symbols)
        self.interval = self._validate_interval(interval)
        self.start_dt = _to_utc_datetime(start)
        self.end_dt = _to_utc_datetime(end)
        if self.end_dt <= self.start_dt:
            raise ValueError("end must be greater than start")
        if market != SUPPORTED_MARKET:
            raise ValueError('Binance BarsReplayFeed currently supports only market="futures"')
        self.market = market
        self.cache_dir = Path(cache_dir)
        self.db_path = self.cache_dir / DEFAULT_DB_NAME
        self.name = name or self._default_name()
        self.refresh = bool(refresh)
        self.cache_only = bool(cache_only)
        self.closed_only = bool(closed_only)
        self._client = BinanceKlineClient()
        self._prepared = False
        self._rows = None

    def prepare(self) -> None:
        if self.cache_only and not self.db_path.exists():
            raise RuntimeError(
                f"Binance cache database does not exist: {self.db_path}. "
                "Run without cache_only first to download data."
            )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        start_ms = _datetime_to_ms(self.start_dt)
        end_ms = _datetime_to_ms(self.end_dt)

        for symbol in self.symbols:
            missing_ranges = [(start_ms, end_ms)] if self.refresh else self._missing_ranges(symbol, start_ms, end_ms)
            if self.cache_only and missing_ranges:
                raise RuntimeError(
                    f"Binance cache is incomplete for {symbol} {self.interval} "
                    f"{self.start_dt.isoformat()} -> {self.end_dt.isoformat()}"
                )
            for range_start, range_end in missing_ranges:
                self._download_range(symbol, range_start, range_end)

        self._rows = self._load_rows(start_ms, end_ms)
        self._prepared = True

    def events(self) -> Iterable[FeedEvent]:
        if not self._prepared:
            self.prepare()
        grouped = OrderedDict()
        for row in self._rows:
            dt = _ms_to_datetime(row["dt_ms"])
            symbol = row["symbol"]
            payload = {
                "dt": dt,
                "symbol": symbol,
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
            for key in ("close_time", "volume_quote", "num_trades", "volume_base_buy", "volume_quote_buy"):
                if row.get(key) is not None:
                    payload[key] = row[key]
            grouped.setdefault(dt, OrderedDict())[symbol] = payload

        for dt, bars in grouped.items():
            prices = OrderedDict((symbol, bar["close"]) for symbol, bar in bars.items())
            yield FeedEvent(event_type="bars", dt=dt, data=bars, prices=prices)

    def close(self) -> None:
        return None

    def _default_name(self) -> str:
        return f"binance:bars:{self.market}:{self.interval}:{','.join(self.symbols)}"

    def _normalize_symbols(self, symbols) -> List[str]:
        if isinstance(symbols, (str, bytes)):
            symbols = [symbols]
        try:
            normalized = [str(symbol).upper() for symbol in symbols]
        except TypeError:
            raise TypeError("symbols must be a symbol string or an iterable of symbols")
        if not normalized or any(not symbol for symbol in normalized):
            raise ValueError("symbols must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("symbols must not contain duplicates")
        return normalized

    def _validate_interval(self, interval: str) -> str:
        interval = str(interval)
        _interval_to_ms(interval)
        return interval

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bars (
                    source TEXT NOT NULL,
                    market TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    dt_ms INTEGER NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    close_time INTEGER,
                    volume_quote REAL,
                    num_trades INTEGER,
                    volume_base_buy REAL,
                    volume_quote_buy REAL,
                    PRIMARY KEY (source, market, symbol, interval, dt_ms)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bar_coverage (
                    source TEXT NOT NULL,
                    market TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    start_ms INTEGER NOT NULL,
                    end_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL,
                    PRIMARY KEY (source, market, symbol, interval, start_ms, end_ms)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_bars_query
                ON bars (source, market, symbol, interval, dt_ms)
                """
            )

    def _missing_ranges(self, symbol: str, start_ms: int, end_ms: int):
        intervals = self._coverage_intervals(symbol)
        missing = []
        cursor = start_ms
        for covered_start, covered_end in intervals:
            if covered_end <= cursor:
                continue
            if covered_start > cursor:
                missing.append((cursor, min(covered_start, end_ms)))
            cursor = max(cursor, covered_end)
            if cursor >= end_ms:
                break
        if cursor < end_ms:
            missing.append((cursor, end_ms))
        return [(start, end) for start, end in missing if start < end]

    def _coverage_intervals(self, symbol: str):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT start_ms, end_ms
                FROM bar_coverage
                WHERE source = ? AND market = ? AND symbol = ? AND interval = ?
                ORDER BY start_ms
                """,
                (SOURCE, self.market, symbol, self.interval),
            ).fetchall()
        return _merge_intervals((row["start_ms"], row["end_ms"]) for row in rows)

    def _download_range(self, symbol: str, start_ms: int, end_ms: int) -> None:
        start_dt = _ms_to_datetime(start_ms)
        end_dt = _ms_to_datetime(end_ms)
        try:
            raw_rows = self._client.fetch_klines(
                symbol,
                self.interval,
                start_dt,
                end_dt,
                chunk_size=DEFAULT_CHUNK_SIZE,
                delay=DEFAULT_DELAY,
            )
        except ImportError as exc:
            raise RuntimeError(
                "crypto_api is required to download Binance futures klines. "
                "Install crypto_api or run with an existing cache."
            ) from exc
        rows = [
            self._normalize_kline(symbol, row)
            for row in raw_rows
            if start_ms <= int(row["open_time"]) < end_ms
        ]
        coverage_end_ms = end_ms
        if self.closed_only:
            now_ms = int(time.time() * 1000)
            coverage_end_ms = min(end_ms, _current_open_time_ms(now_ms, self.interval))
            rows = [row for row in rows if row.get("close_time") is None or row["close_time"] < now_ms]
        if coverage_end_ms > start_ms:
            self._write_rows_and_coverage(symbol, rows, start_ms, coverage_end_ms)
        elif rows:
            self._write_rows(rows)

    def _normalize_kline(self, symbol: str, row: dict) -> dict:
        required = ("open_time", "open", "high", "low", "close", "volume")
        missing = [key for key in required if key not in row]
        if missing:
            raise ValueError(f"Binance kline row missing fields: {missing}")
        return {
            "source": SOURCE,
            "market": self.market,
            "symbol": symbol,
            "interval": self.interval,
            "dt_ms": int(row["open_time"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "close_time": _optional_int(row.get("close_time")),
            "volume_quote": _optional_float(row.get("volume_quote")),
            "num_trades": _optional_int(row.get("num_trades")),
            "volume_base_buy": _optional_float(row.get("volume_base_buy")),
            "volume_quote_buy": _optional_float(row.get("volume_quote_buy")),
        }

    def _write_rows_and_coverage(self, symbol: str, rows: List[dict], start_ms: int, end_ms: int) -> None:
        with self._connect() as conn:
            with conn:
                self._write_rows_with_connection(conn, rows)
                self._replace_coverage(conn, symbol, start_ms, end_ms)

    def _write_rows(self, rows: List[dict]) -> None:
        with self._connect() as conn:
            with conn:
                self._write_rows_with_connection(conn, rows)

    def _write_rows_with_connection(self, conn, rows: List[dict]) -> None:
        if not rows:
            return
        conn.executemany(
            """
            INSERT OR REPLACE INTO bars (
                source, market, symbol, interval, dt_ms,
                open, high, low, close, volume,
                close_time, volume_quote, num_trades,
                volume_base_buy, volume_quote_buy
            )
            VALUES (
                :source, :market, :symbol, :interval, :dt_ms,
                :open, :high, :low, :close, :volume,
                :close_time, :volume_quote, :num_trades,
                :volume_base_buy, :volume_quote_buy
            )
            """,
            rows,
        )

    def _replace_coverage(self, conn, symbol: str, start_ms: int, end_ms: int) -> None:
        rows = conn.execute(
            """
            SELECT start_ms, end_ms
            FROM bar_coverage
            WHERE source = ? AND market = ? AND symbol = ? AND interval = ?
            ORDER BY start_ms
            """,
            (SOURCE, self.market, symbol, self.interval),
        ).fetchall()
        intervals = _merge_intervals(
            [(row["start_ms"], row["end_ms"]) for row in rows] + [(start_ms, end_ms)]
        )
        conn.execute(
            """
            DELETE FROM bar_coverage
            WHERE source = ? AND market = ? AND symbol = ? AND interval = ?
            """,
            (SOURCE, self.market, symbol, self.interval),
        )
        now_ms = int(time.time() * 1000)
        conn.executemany(
            """
            INSERT INTO bar_coverage (
                source, market, symbol, interval, start_ms, end_ms, updated_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [(SOURCE, self.market, symbol, self.interval, start, end, now_ms) for start, end in intervals],
        )

    def _load_rows(self, start_ms: int, end_ms: int) -> List[dict]:
        placeholders = ",".join("?" for _ in self.symbols)
        sql = f"""
            SELECT *
            FROM bars
            WHERE source = ?
              AND market = ?
              AND interval = ?
              AND symbol IN ({placeholders})
              AND dt_ms >= ?
              AND dt_ms < ?
            ORDER BY dt_ms, symbol
        """
        params = [SOURCE, self.market, self.interval, *self.symbols, start_ms, end_ms]
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]


def _to_utc_datetime(value) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.to_pydatetime()


def _datetime_to_ms(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def _ms_to_datetime(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def _interval_to_ms(interval: str) -> int:
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    if len(interval) < 2 or interval[-1] not in units:
        raise ValueError("interval must be like '1m', '5m', '1h', or '1d'")
    amount = int(interval[:-1])
    if amount <= 0:
        raise ValueError("interval amount must be positive")
    return amount * units[interval[-1]]


def _current_open_time_ms(now_ms: int, interval: str) -> int:
    interval_ms = _interval_to_ms(interval)
    return (int(now_ms) // interval_ms) * interval_ms


def _optional_float(value):
    if value is None:
        return None
    return float(value)


def _optional_int(value):
    if value is None:
        return None
    return int(float(value))


def _merge_intervals(intervals):
    merged = []
    for start, end in sorted((int(start), int(end)) for start, end in intervals):
        if start >= end:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
    return merged


def _fetch_futures_klines_http(symbol: str, interval: str, start_dt, end_dt, chunk_size: int, delay: float):
    symbol = symbol.upper()
    start_ms = _datetime_to_ms(_to_utc_datetime(start_dt))
    end_ms = _datetime_to_ms(_to_utc_datetime(end_dt))
    limit = min(int(chunk_size), DEFAULT_CHUNK_SIZE)
    rows = []
    cursor = start_ms

    while cursor < end_ms:
        raw_rows = _http_get_json(
            f"{FUTURES_API_BASE}/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms - 1,
                "limit": limit,
            },
        )
        if not raw_rows:
            break
        for row in raw_rows:
            normalized = _raw_kline_to_dict(row)
            if normalized["open_time"] >= end_ms:
                break
            rows.append(normalized)
        next_cursor = int(raw_rows[-1][0]) + _interval_to_ms(interval)
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if cursor < end_ms and delay > 0:
            time.sleep(delay)
    return rows


def _http_get_json(url: str, params: dict):
    query = urlencode(params)
    full_url = f"{url}?{query}" if query else url
    with urlopen(full_url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _raw_kline_to_dict(row: list) -> dict:
    return {
        "open_time": int(row[0]),
        "open": float(row[1]),
        "high": float(row[2]),
        "low": float(row[3]),
        "close": float(row[4]),
        "volume": float(row[5]),
        "close_time": int(row[6]),
        "volume_quote": float(row[7]),
        "num_trades": int(row[8]),
        "volume_base_buy": float(row[9]),
        "volume_quote_buy": float(row[10]),
        "ignored": row[11] if len(row) > 11 else "0",
    }
