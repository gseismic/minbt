import datetime as _dt
import math
import numbers
import sys
from dataclasses import dataclass
from datetime import timezone
from typing import Any, Optional, Tuple

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # Python 3.8 compatibility
    from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _to_datetime(value):
    if value is None:
        return None
    if isinstance(value, numbers.Number):
        return None
    if isinstance(value, _dt.datetime):
        return value
    if isinstance(value, _dt.date):
        return _dt.datetime.combine(value, _dt.time())
    try:
        import pandas as pd

        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            return None
        if getattr(timestamp, "nanosecond", 0):
            timestamp = timestamp.floor("us")
        return timestamp.to_pydatetime()
    except (ValueError, TypeError, OverflowError):
        return None


def _to_time(value) -> _dt.time:
    if isinstance(value, _dt.time):
        return value
    if isinstance(value, str):
        hour, minute, *rest = value.split(":")
        second = int(rest[0]) if rest else 0
        return _dt.time(int(hour), int(minute), second)
    raise TypeError(f"invalid time value: {value!r}")


def _is_multiple(value: float, step: Optional[float]) -> bool:
    if step is None:
        return True
    if not math.isfinite(value) or not math.isfinite(step) or step <= 0:
        return False
    ratio = value / step
    if not math.isfinite(ratio):
        return False
    nearest = round(ratio)
    represented = nearest * step
    if not math.isfinite(represented):
        return False
    tolerance = 4 * max(
        _float_ulp(value),
        _float_ulp(represented),
        abs(nearest) * _float_ulp(step),
    )
    return abs(value - represented) <= tolerance


def _float_ulp(value: float) -> float:
    """返回浮点数附近的间距，兼容 Python 3.8（math.ulp 从 3.9 才提供）。"""
    if value == 0:
        return float.fromhex("0x0.0000000000001p-1022")
    _, exponent = math.frexp(abs(value))
    return max(
        float.fromhex("0x0.0000000000001p-1022"),
        math.ldexp(1.0, exponent - sys.float_info.mant_dig),
    )


@dataclass
class OrderValidation:
    ok: bool
    message: str = ""


@dataclass
class Market:
    """市场特征配置。

    ``timezone`` 是 IANA 时区名；无时区的 datetime 按 UTC 解释，再转换到该市场时区。
    """

    name: str = "Default"
    allow_short: bool = True
    t_plus: int = 0
    lot_size: Optional[float] = None
    tick_size: Optional[float] = None
    min_qty: Optional[float] = None
    min_notional: Optional[float] = None
    require_dt: bool = False
    weekdays_only: bool = False
    trading_sessions: Optional[Tuple[Tuple[Any, Any], ...]] = None
    allow_daily_bar: bool = True
    timezone: str = "UTC"

    def __post_init__(self):
        if self.t_plus not in (0, 1):
            raise ValueError(f"only T+0/T+1 market is supported, got T+{self.t_plus}")
        if not isinstance(self.timezone, str) or not self.timezone:
            raise ValueError("timezone must be a non-empty IANA time zone name")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown market timezone: {self.timezone!r}") from exc
        for field_name in ("lot_size", "tick_size", "min_qty", "min_notional"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, numbers.Real):
                raise TypeError(f"{field_name} must be a finite positive number or None")
            if not math.isfinite(float(value)) or value <= 0:
                raise ValueError(f"{field_name} must be a finite positive number or None")
        if self.trading_sessions is not None:
            self.trading_sessions = tuple(
                (_to_time(start), _to_time(end))
                for start, end in self.trading_sessions
            )

    def _local_datetime(self, dt):
        value = _to_datetime(dt)
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(ZoneInfo(self.timezone))

    def is_trading_time(self, dt) -> bool:
        raw_value = _to_datetime(dt)
        value = self._local_datetime(dt)
        if value is None:
            return not self.require_dt and not self.weekdays_only and not self.trading_sessions
        if self.weekdays_only and value.weekday() >= 5:
            return False
        if not self.trading_sessions:
            return True
        if self.allow_daily_bar and (
            value.time() == _dt.time()
            or (raw_value is not None and raw_value.time() == _dt.time())
        ):
            return True
        return any(start <= value.time() <= end for start, end in self.trading_sessions)

    def trading_day(self, dt):
        value = self._local_datetime(dt)
        if value is None:
            return None
        return value.date()

    def on_new_dt(self, broker, dt, symbols=None) -> None:
        if self.t_plus == 0:
            return
        current_day = self.trading_day(dt)
        if current_day is None:
            return
        symbol_set = None if symbols is None else set(symbols)
        for portfolio in broker.portfolios.values():
            for symbol, position in portfolio.positions.items():
                if symbol_set is not None and symbol not in symbol_set:
                    continue
                position.unlock_before(current_day)

    def normalize_order_qty(
        self,
        broker,
        symbol: str,
        qty: float,
        price: Optional[float] = None,
        portfolio: str = "main",
    ) -> float:
        if qty <= 0 or self.lot_size is None:
            return qty
        position = broker.get_position(symbol, portfolio=portfolio)
        current_size = 0 if position is None else position.size
        if current_size < 0:
            return qty
        ratio = abs(qty) / self.lot_size
        if not math.isfinite(ratio):
            raise ValueError("target quantity divided by lot_size must be finite")
        nearest = round(ratio)
        units = nearest if _is_multiple(abs(qty), self.lot_size) else math.floor(ratio)
        normalized = units * self.lot_size
        return float(normalized)

    def validate_order(self, broker, symbol: str, qty: float, price: float, dt=None, portfolio: str = "main") -> OrderValidation:
        if not math.isfinite(qty):
            return OrderValidation(False, "qty must be finite")
        if not math.isfinite(price):
            return OrderValidation(False, "price must be finite")
        if qty == 0:
            return OrderValidation(False, "qty must be non-zero")
        if price <= 0:
            return OrderValidation(False, "price must be positive")
        if not self.is_trading_time(dt):
            return OrderValidation(False, f"not in trading time: {dt}")
        if self.min_qty is not None and abs(qty) < self.min_qty:
            return OrderValidation(False, f"qty below min_qty: {qty} < {self.min_qty}")
        notional = abs(qty) * price
        if self.min_notional is not None and notional < self.min_notional:
            return OrderValidation(False, f"notional below min_notional: {notional} < {self.min_notional}")
        if self.lot_size is not None and not _is_multiple(abs(qty), self.lot_size):
            return OrderValidation(False, f"qty must be multiple of lot_size {self.lot_size}: {qty}")
        if self.tick_size is not None and not _is_multiple(price, self.tick_size):
            return OrderValidation(False, f"price must be multiple of tick_size {self.tick_size}: {price}")

        position = broker.get_position(symbol, portfolio=portfolio)
        current_size = 0 if position is None else position.size
        new_size = current_size + qty
        if not self.allow_short and new_size < -1e-12:
            return OrderValidation(False, f"short is not allowed: {symbol}")
        if position is not None and current_size * qty < 0:
            close_size = min(abs(qty), abs(current_size))
            if close_size > position.available_size + 1e-12:
                return OrderValidation(
                    False,
                    f"insufficient available position: qty={close_size}, available={position.available_size}",
                )
        return OrderValidation(True)

    def on_order_filled(
        self,
        broker,
        symbol: str,
        qty: float,
        price: float,
        dt=None,
        portfolio: str = "main",
        old_size: float = 0.0,
    ) -> None:
        if self.t_plus == 0 or qty <= 0:
            return
        position = broker.get_position(symbol, portfolio=portfolio)
        if position is None or position.size <= 0:
            return
        new_long_size = max(position.size, 0.0)
        old_long_size = max(old_size, 0.0)
        opened_size = max(0.0, new_long_size - old_long_size)
        position.lock_size(opened_size, self.trading_day(dt))
