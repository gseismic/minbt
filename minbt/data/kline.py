"""Kline 专用读取辅助。

Kline 是一种 Bar。这里的解析逻辑只服务 Binance Kline 行格式，不定义通用 Bar 的字段集合。
"""

from datetime import datetime, timezone
from typing import Iterable, Mapping

from .model import Bar, normalize_datetime


OPTIONAL_BAR_FIELDS = (
    "close_time",
    "volume_quote",
    "num_trades",
    "volume_base_buy",
    "volume_quote_buy",
)


def normalize_symbols(symbols, *, allow_none=False):
    if symbols is None and allow_none:
        return None
    if isinstance(symbols, (str, bytes)):
        symbols = [symbols]
    try:
        normalized = [str(symbol).strip().upper() for symbol in symbols]
    except TypeError as exc:
        raise TypeError("symbols must be a symbol string or an iterable of symbols") from exc
    if not normalized or any(not symbol for symbol in normalized):
        raise ValueError("symbols must not be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError("symbols must not contain duplicates")
    return normalized


def to_utc_datetime(value) -> datetime:
    return normalize_datetime(value)


def datetime_to_ms(value: datetime) -> int:
    normalized = normalize_datetime(value)
    return int(normalized.timestamp() * 1000)


def ms_to_datetime(value: int) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)


def optional_float(value):
    if value is None or value == "":
        return None
    return float(value)


def optional_int(value):
    if value is None or value == "":
        return None
    return int(float(value))


class _KlineRowFeed:
    """把有序 Kline 行转换为逐条 `Bar(kind="kline")`。"""

    supports_preload = True
    supports_incremental = True
    ordered = True
    replayable = True

    def events(self) -> Iterable[Bar]:
        if not getattr(self, "_prepared", False):
            self.prepare()

        row_stream = iter(self._row_stream())
        previous_dt_ms = None
        current_dt_ms = None
        current_symbols = set()
        try:
            for raw_row in row_stream:
                row = self._normalize_row(raw_row)
                dt_ms = row.pop("dt_ms")
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
            symbol = str(raw_row["symbol"]).strip().upper()
            if not symbol:
                raise ValueError("symbol must not be empty")
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
