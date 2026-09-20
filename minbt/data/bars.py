from collections import OrderedDict
from datetime import datetime, timezone
from typing import Iterable, Mapping

import pandas as pd

from .feed import FeedEvent


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
        normalized = [str(symbol).upper() for symbol in symbols]
    except TypeError as exc:
        raise TypeError("symbols must be a symbol string or an iterable of symbols") from exc
    if not normalized or any(not symbol for symbol in normalized):
        raise ValueError("symbols must not be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError("symbols must not contain duplicates")
    return normalized


def to_utc_datetime(value) -> datetime:
    """将常见时间对象转换为 UTC datetime；arrow 对象按其 datetime 属性处理。"""
    # arrow 的 .datetime 是 property（返回 datetime 实例），不能当作可调用对象判断
    candidate = getattr(value, "datetime", None)
    if isinstance(candidate, datetime) and not isinstance(value, datetime):
        value = candidate
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.to_pydatetime()


def datetime_to_ms(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


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
    """把有序的 K 线行流转换为按 dt 聚合的 bars FeedEvent。"""

    event_type = "bars"
    streaming = True

    def events(self) -> Iterable[FeedEvent]:
        if not getattr(self, "_prepared", False):
            self.prepare()

        row_stream = iter(self._row_stream())
        current_dt_ms = None
        current_bars = {}
        try:
            for raw_row in row_stream:
                row = self._normalize_row(raw_row)
                dt_ms = row["dt_ms"]
                symbol = row["symbol"]

                if current_dt_ms is not None and dt_ms < current_dt_ms:
                    raise ValueError(
                        f"{self.name} data is not ordered by dt: "
                        f"{dt_ms} came after {current_dt_ms}"
                    )

                if current_dt_ms is None:
                    current_dt_ms = dt_ms
                elif dt_ms != current_dt_ms:
                    yield self._make_event(current_dt_ms, current_bars)
                    current_dt_ms = dt_ms
                    current_bars = {}

                if symbol in current_bars:
                    raise ValueError(
                        f"{self.name} data contains duplicate ({ms_to_datetime(dt_ms)!r}, {symbol!r}) rows"
                    )
                row.pop("dt_ms")
                current_bars[symbol] = row

            if current_dt_ms is not None:
                yield self._make_event(current_dt_ms, current_bars)
        finally:
            close = getattr(row_stream, "close", None)
            if callable(close):
                close()

    def _make_event(self, dt_ms: int, bars: Mapping[str, dict]) -> FeedEvent:
        ordered_bars = OrderedDict((symbol, bars[symbol]) for symbol in sorted(bars))
        prices = OrderedDict((symbol, row["close"]) for symbol, row in ordered_bars.items())
        return FeedEvent(
            event_type="bars",
            dt=ms_to_datetime(dt_ms),
            data=ordered_bars,
            prices=prices,
        )

    def _normalize_row(self, raw_row: Mapping) -> dict:
        if not isinstance(raw_row, Mapping):
            raise TypeError(f"{self.name} row must be a mapping")
        required = ("dt_ms", "symbol", "open", "high", "low", "close", "volume")
        missing = [field for field in required if field not in raw_row]
        if missing:
            raise ValueError(f"{self.name} row missing fields: {missing}")

        try:
            dt_ms = int(raw_row["dt_ms"])
            symbol = str(raw_row["symbol"]).upper()
            if not symbol:
                raise ValueError("symbol must not be empty")
            row = {
                "dt_ms": dt_ms,
                "dt": ms_to_datetime(dt_ms),
                "symbol": symbol,
                "open": float(raw_row["open"]),
                "high": float(raw_row["high"]),
                "low": float(raw_row["low"]),
                "close": float(raw_row["close"]),
                "volume": float(raw_row["volume"]),
            }
            for field in OPTIONAL_BAR_FIELDS:
                if field not in raw_row or raw_row[field] is None:
                    continue
                value = optional_int(raw_row[field]) if field in ("close_time", "num_trades") else optional_float(raw_row[field])
                if value is not None:
                    row[field] = value
            return row
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{self.name} row contains invalid bar values: {raw_row!r}") from exc

    def prepare(self) -> None:
        self._prepared = True

    def close(self) -> None:
        """子类可覆盖；重复 close 必须安全。"""
        return None
