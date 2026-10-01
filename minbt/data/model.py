"""minbt 的最小市场数据模型。

Bar 只描述市场观测，不携带估值优先级或账户状态。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import math
from numbers import Number
from types import MappingProxyType
from typing import Any, Optional, Union

import pandas as pd


def normalize_datetime(value: Any, *, unit: Optional[str] = None) -> datetime:
    """把常见时间输入统一为 UTC datetime。

    无时区输入按 UTC 解释。Exchange 使用统一到毫秒的时间键做批次边界判断，
    但仍保留 datetime 作为公开字段。数字输入默认按数量级推断秒、毫秒、微秒或纳秒；
    对有歧义的时间戳可通过 ``unit="s"/"ms"/"us"/"ns"`` 显式指定单位。
    """

    try:
        if isinstance(value, Number) and not isinstance(value, bool):
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError("datetime number must be finite")
            if unit is not None:
                if unit not in {"s", "ms", "us", "ns"}:
                    raise ValueError("unit must be one of 's', 'ms', 'us', or 'ns'")
                timestamp_unit = unit
            else:
                magnitude = abs(numeric)
                if magnitude >= 1e17:
                    timestamp_unit = "ns"
                elif magnitude >= 1e14:
                    timestamp_unit = "us"
                elif magnitude >= 1e11:
                    timestamp_unit = "ms"
                else:
                    timestamp_unit = "s"
            timestamp = pd.Timestamp(value, unit=timestamp_unit, tz="UTC")
        elif unit is not None:
            raise ValueError("unit can only be specified for a numeric datetime value")
        elif isinstance(value, datetime):
            timestamp = pd.Timestamp(value)
        elif isinstance(value, date):
            timestamp = pd.Timestamp(datetime.combine(value, time()))
        else:
            timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            raise ValueError("datetime must not be NaT")
        result = timestamp.to_pydatetime()
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"invalid datetime value: {value!r} ({exc})") from exc

    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    else:
        result = result.astimezone(timezone.utc)
    # 第一阶段统一到毫秒，避免不同来源以不同精度拆分同一个批次。
    return result.replace(microsecond=(result.microsecond // 1000) * 1000)


def datetime_key(value: datetime) -> int:
    """返回用于排序和批次比较的 UTC 毫秒键。"""

    normalized = normalize_datetime(value)
    return int(normalized.timestamp() * 1000)


def _freeze_payload(value: Any) -> Any:
    """递归冻结常见容器，避免来源继续修改已发出的数据。"""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_payload(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_payload(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_payload(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_payload(item) for item in value)
    return value


@dataclass(frozen=True)
class Bar:
    """一个时间点、一个 symbol 的市场观测。"""

    dt: datetime
    symbol: str
    kind: str
    data: Any

    def __post_init__(self) -> None:
        dt = normalize_datetime(self.dt)
        if self.symbol is None:
            raise ValueError("Bar.symbol must not be None")
        if self.kind is None:
            raise ValueError("Bar.kind must not be None")
        symbol = str(self.symbol).strip().upper()
        kind = str(self.kind).strip().lower()
        if not symbol:
            raise ValueError("Bar.symbol must not be empty")
        if not kind:
            raise ValueError("Bar.kind must not be empty")
        object.__setattr__(self, "dt", dt)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "data", _freeze_payload(self.data))


@dataclass(frozen=True)
class News:
    """不参与默认估值的时间事件。"""

    dt: datetime
    data: Any
    symbol: Union[str, None] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "dt", normalize_datetime(self.dt))
        if self.symbol is not None:
            symbol = str(self.symbol).strip().upper()
            object.__setattr__(self, "symbol", symbol or None)
        object.__setattr__(self, "data", _freeze_payload(self.data))


MarketEvent = Union[Bar, News]


__all__ = ["Bar", "News", "MarketEvent", "normalize_datetime", "datetime_key"]
