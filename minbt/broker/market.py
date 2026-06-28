import datetime as _dt
from dataclasses import dataclass
from typing import Optional, Any


def _to_datetime(value):
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value
    if isinstance(value, _dt.date):
        return _dt.datetime.combine(value, _dt.time())
    try:
        import pandas as pd

        return pd.Timestamp(value).to_pydatetime()
    except Exception:
        return None


def _is_multiple(value: float, step: Optional[float]) -> bool:
    if step is None or step == 0:
        return True
    ratio = value / step
    return abs(ratio - round(ratio)) < 1e-9


@dataclass
class OrderValidation:
    ok: bool
    message: str = ""


class MarketModel:
    """最小市场规则模型，负责校验订单和维护市场相关持仓状态。"""

    allow_short = True
    lot_size = None
    tick_size = None
    min_qty = None
    min_notional = None

    def is_trading_time(self, dt) -> bool:
        return True

    def trading_day(self, dt):
        value = _to_datetime(dt)
        if value is None:
            return None
        return value.date()

    def on_new_dt(self, broker, dt) -> None:
        return None

    def normalize_order_qty(self, symbol: str, qty: float) -> float:
        return qty

    def validate_order(self, broker, symbol: str, qty: float, price: float, dt=None, portfolio_id: str = "default") -> OrderValidation:
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

        position = broker.get_position(symbol, portfolio_id=portfolio_id, create_if_missing=False)
        current_size = 0 if position is None else position.size
        new_size = current_size + qty
        if not self.allow_short and new_size < -1e-12:
            return OrderValidation(False, f"short is not allowed: {symbol}")
        if position is not None and current_size * qty < 0 and abs(qty) <= abs(current_size):
            if abs(qty) > position.available_size + 1e-12:
                return OrderValidation(
                    False,
                    f"insufficient available position: qty={abs(qty)}, available={position.available_size}",
                )
        return OrderValidation(True)

    def on_order_filled(self, broker, symbol: str, qty: float, price: float, dt=None, portfolio_id: str = "default") -> None:
        return None


class SimpleMarket(MarketModel):
    """默认市场：保持当前 T+0 市价成交行为。"""

    allow_short = True


class CryptoMarket(SimpleMarket):
    """加密资产市场预设：T+0，允许配置最小数量和价格精度。"""

    def __init__(
        self,
        *,
        min_qty: Optional[float] = None,
        min_notional: Optional[float] = None,
        tick_size: Optional[float] = None,
        allow_short: bool = True,
    ):
        self.min_qty = min_qty
        self.min_notional = min_notional
        self.tick_size = tick_size
        self.allow_short = allow_short


class ChinaAStockMarket(MarketModel):
    """A 股市场最小预设：交易日、交易时间、100 股一手、T+1、不可做空。"""

    allow_short = False

    def __init__(self, *, lot_size: int = 100, tick_size: float = 0.01):
        self.lot_size = lot_size
        self.tick_size = tick_size

    def is_trading_time(self, dt) -> bool:
        value = _to_datetime(dt)
        if value is None:
            return True
        if value.weekday() >= 5:
            return False
        # 日线数据经常用 00:00:00 表示交易日，视为可交易。
        if value.time() == _dt.time():
            return True
        morning = _dt.time(9, 30) <= value.time() <= _dt.time(11, 30)
        afternoon = _dt.time(13, 0) <= value.time() <= _dt.time(15, 0)
        return morning or afternoon

    def on_new_dt(self, broker, dt) -> None:
        current_day = self.trading_day(dt)
        if current_day is None:
            return
        for portfolio in broker.portfolios.values():
            for position in portfolio.positions.values():
                position.unlock_before(current_day)

    def validate_order(self, broker, symbol: str, qty: float, price: float, dt=None, portfolio_id: str = "default") -> OrderValidation:
        base = super().validate_order(broker, symbol, qty, price, dt=dt, portfolio_id=portfolio_id)
        if not base.ok:
            return base
        position = broker.get_position(symbol, portfolio_id=portfolio_id, create_if_missing=False)
        current_size = 0 if position is None else position.size
        is_buy_open = qty > 0 and current_size >= 0
        if is_buy_open and not _is_multiple(abs(qty), self.lot_size):
            return OrderValidation(False, f"buy qty must be multiple of lot_size {self.lot_size}: {qty}")
        return OrderValidation(True)

    def on_order_filled(self, broker, symbol: str, qty: float, price: float, dt=None, portfolio_id: str = "default") -> None:
        if qty <= 0:
            return
        position = broker.get_position(symbol, portfolio_id=portfolio_id, create_if_missing=False)
        if position is None or position.size <= 0:
            return
        position.lock_size(abs(qty), self.trading_day(dt))

