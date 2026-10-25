"""Binance K 线的无状态字段与时间转换。"""

from datetime import datetime, timedelta, timezone

from ...data.model import datetime_key, normalize_datetime, normalize_symbol


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


__all__ = [
    "OPTIONAL_BAR_FIELDS",
    "normalize_symbols",
    "to_utc_datetime",
    "datetime_to_ms",
    "ms_to_datetime",
    "optional_float",
    "optional_int",
]
