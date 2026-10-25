"""Binance SDK 账户薄适配；账户生命周期由调用者管理。"""

from decimal import Decimal
from threading import get_ident

from ..._validation import finite_number
from ...data.model import normalize_symbol


class Broker:
    """借用 SDK 账户，仅适配有符号市价数量与单向净持仓。"""

    def __init__(self, sdk_broker):
        self.sdk = sdk_broker
        self._exchange = None
        self._failed = False

    def submit_market_order(self, symbol: str, qty: float) -> dict:
        owner = self._exchange
        if (
            owner is None or owner._state != "running" or self._failed
            or owner._callback_thread != get_ident()
        ):
            raise RuntimeError("orders require an active on_bars callback and a healthy Broker")
        symbol = normalize_symbol(symbol)
        if symbol != owner.symbol:
            raise ValueError("order symbol must match the live Exchange")
        finite_number(qty, "qty")
        if qty == 0:
            raise ValueError("qty must not be zero")
        amount = Decimal(str(qty))
        try:
            return self.sdk.submit_market_order(
                symbol, "BUY" if amount > 0 else "SELL", amount.copy_abs()
            )
        except BaseException:
            self._failed = True  # 包含中断；未知写入结果不自动重发。
            raise

    def get_position_size(self, symbol: str) -> float:
        symbol = normalize_symbol(symbol)
        rows = self.sdk.get_positions(symbol)
        if not isinstance(rows, list) or len(rows) > 1:
            raise ValueError("expected at most one one-way position")
        if not rows:
            return 0.0
        row = rows[0]
        if row["symbol"] != symbol or row["positionSide"] != "BOTH":
            raise ValueError("expected a matching one-way BOTH position")
        return finite_number(float(row["positionAmt"]), "positionAmt")
