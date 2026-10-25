"""Kline 专用读取辅助。

Kline 是一种 Bar。这里的解析逻辑只服务 Binance Kline 行格式，不定义通用 Bar 的字段集合。
"""

from datetime import datetime, timedelta, timezone
from itertools import groupby
from typing import Iterable, Mapping
import warnings

from ...data.model import Bar, datetime_key, normalize_datetime, normalize_symbol


OPTIONAL_BAR_FIELDS = (
    "close_time",
    "volume_quote",
    "num_trades",
    "volume_base_buy",
    "volume_quote_buy",
)


def normalize_symbols(symbols, *, allow_none=False, allow_wildcard=False):
    if symbols is None and allow_none:
        return None
    if isinstance(symbols, (str, bytes)):
        symbols = [symbols]
    try:
        normalized = [normalize_symbol(symbol) for symbol in symbols]
    except TypeError as exc:
        raise TypeError("symbols must be a symbol string or an iterable of symbols") from exc
    if not normalized or any(not symbol for symbol in normalized):
        raise ValueError("symbols must not be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError("symbols must not contain duplicates")
    if allow_wildcard and "*" in normalized:
        if normalized != ["*"]:
            raise ValueError("'*' must be used alone in symbols")
        return None
    return normalized


def to_utc_datetime(value) -> datetime:
    return normalize_datetime(value)


def datetime_to_ms(value: datetime) -> int:
    return datetime_key(value)


def ms_to_datetime(value: int) -> datetime:
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=int(value))


def optional_float(value):
    if value is None or value == "":
        return None
    return float(value)


def optional_int(value):
    if value is None or value == "":
        return None
    return int(float(value))


class _MinuteContinuity:
    """从首次出现开始检查；已报告的 symbol 不再跟踪，避免下架后反复告警。"""

    def __init__(self, name):
        self.name = name
        self.last_seen = {}
        self.warned = set()

    def check_batch(self, open_time, symbols):
        for symbol in list(self.last_seen):
            expected = self.last_seen[symbol] + 60_000
            if expected < open_time or (expected == open_time and symbol not in symbols):
                self._warn(symbol)
        for symbol in symbols - self.warned:
            self.last_seen[symbol] = open_time

    def finish(self, end_ms):
        if end_ms is not None:
            for symbol in list(self.last_seen):
                if self.last_seen[symbol] + 60_000 < end_ms:
                    self._warn(symbol)

    def _warn(self, symbol):
        last = self.last_seen.pop(symbol)
        self.warned.add(symbol)
        warnings.warn(
            f"{self.name}: {symbol} 1m Kline missing; "
            f"first missing open_time={ms_to_datetime(last + 60_000).isoformat()}, "
            f"last seen open_time={ms_to_datetime(last).isoformat()}. "
            "Check database gaps or delisting; only the first gap per symbol is reported.",
            RuntimeWarning,
            stacklevel=3,
        )


class _KlineRowFeed:
    """按收盘时间发布完整 Kline，防止混合回放提前看到区间最终数据。"""

    supports_preload = True
    supports_incremental = True
    ordered = True
    replayable = True
    _warn_minute_gaps = True

    def events(self) -> Iterable[Bar]:
        if not getattr(self, "_prepared", False):
            self.prepare()

        bars = iter(self._iter_bars())
        try:
            if self.interval != "1m" or not self._warn_minute_gaps:
                yield from bars
                return

            continuity = _MinuteContinuity(self.name)
            # 等同一分钟内所有 symbol 到齐后再检查，最多缓冲一个时间截面。
            for open_time, group in groupby(bars, key=lambda bar: bar.data["open_time"]):
                batch = list(group)
                continuity.check_batch(open_time, {bar.symbol for bar in batch})
                yield from batch
            end_dt = getattr(self, "end_dt", None)
            continuity.finish(datetime_to_ms(end_dt) if end_dt is not None else None)
        finally:
            bars.close()

    def _iter_bars(self) -> Iterable[Bar]:
        row_stream = iter(self._row_stream())
        previous_dt_ms = None
        current_dt_ms = None
        current_symbols = set()
        try:
            for raw_row in row_stream:
                row = self._normalize_row(raw_row)
                row.pop("dt_ms")
                dt_ms = row["close_time"]
                symbol = row.pop("symbol")
                if previous_dt_ms is not None and dt_ms < previous_dt_ms:
                    raise ValueError(
                        f"{self.name} data is not ordered by dt: "
                        f"{dt_ms} came after {previous_dt_ms}"
                    )
                if current_dt_ms != dt_ms:
                    current_dt_ms = dt_ms
                    current_symbols = set()
                if symbol in current_symbols:
                    raise ValueError(
                        f"{self.name} data contains duplicate "
                        f"({ms_to_datetime(dt_ms)!r}, {symbol!r}) rows"
                    )
                current_symbols.add(symbol)
                previous_dt_ms = dt_ms
                yield Bar(
                    dt=ms_to_datetime(dt_ms),
                    symbol=symbol,
                    kind="kline",
                    data=row,
                )
        finally:
            close = getattr(row_stream, "close", None)
            if callable(close):
                close()

    def _normalize_row(self, raw_row: Mapping) -> dict:
        if not isinstance(raw_row, Mapping):
            raise TypeError(f"{self.name} row must be a mapping")
        required = ("dt_ms", "symbol")
        missing = [field for field in required if field not in raw_row]
        if missing:
            raise ValueError(f"{self.name} row missing fields: {missing}")

        try:
            dt_ms = int(raw_row["dt_ms"])
            if raw_row["symbol"] is None:
                raise ValueError("symbol must not be None")
            symbol = normalize_symbol(raw_row["symbol"])
            row = {
                key: value
                for key, value in raw_row.items()
                if key not in ("dt_ms", "dt", "symbol")
            }
            for field in ("open", "high", "low", "close", "volume", "volume_quote", "volume_base_buy"):
                if field in row and row[field] is not None:
                    row[field] = float(row[field])
            for field in ("close_time", "num_trades"):
                if field in row and row[field] is not None:
                    row[field] = int(float(row[field]))
            if row.get("close_time") is None or row["close_time"] <= dt_ms:
                raise ValueError("close_time must be present and greater than open_time")
            row["open_time"] = dt_ms
            return {"dt_ms": dt_ms, "symbol": symbol, **row}
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{self.name} row contains invalid bar values: {raw_row!r}") from exc

    def prepare(self) -> None:
        self._prepared = True

    def close(self) -> None:
        """子类可覆盖；重复 close 必须安全。"""
        return None


__all__ = [
    "OPTIONAL_BAR_FIELDS",
    "normalize_symbols",
    "to_utc_datetime",
    "datetime_to_ms",
    "ms_to_datetime",
    "optional_float",
    "optional_int",
]
