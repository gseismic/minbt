import datetime as _dt
import math
import numbers
from dataclasses import dataclass
from typing import Any, Optional, Tuple


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
    except Exception:
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
    if step is None or step == 0:
        return True
    ratio = value / step
    return abs(ratio - round(ratio)) < 1e-9


@dataclass
class OrderValidation:
    ok: bool
    message: str = ""


@dataclass
class Market:
    """市场特征配置，负责订单校验和市场相关持仓状态维护。"""

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

    def __post_init__(self):
        if self.t_plus not in (0, 1):
            raise ValueError(f"only T+0/T+1 market is supported, got T+{self.t_plus}")
        if self.trading_sessions is not None:
            self.trading_sessions = tuple(
                (_to_time(start), _to_time(end))
                for start, end in self.trading_sessions
            )

    def is_trading_time(self, dt) -> bool:
        value = _to_datetime(dt)
        if value is None:
            return not self.require_dt and not self.weekdays_only and not self.trading_sessions
        if self.weekdays_only and value.weekday() >= 5:
            return False
        if not self.trading_sessions:
            return True
        if self.allow_daily_bar and value.time() == _dt.time():
            return True
        return any(start <= value.time() <= end for start, end in self.trading_sessions)

    def trading_day(self, dt):
        value = _to_datetime(dt)
        if value is None:
            return None
        return value.date()

    def on_new_dt(self, broker, dt) -> None:
        if self.t_plus == 0:
            return
        current_day = self.trading_day(dt)
        if current_day is None:
            return
        for portfolio in broker.portfolios.values():
            for position in portfolio.positions.values():
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
        normalized = math.floor(abs(qty) / self.lot_size + 1e-12) * self.lot_size
        return float(normalized)

    def validate_order(self, broker, symbol: str, qty: float, price: float, dt=None, portfolio: str = "main") -> OrderValidation:
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
