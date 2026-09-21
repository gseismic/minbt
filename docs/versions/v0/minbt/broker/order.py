from dataclasses import dataclass
from typing import Any, Literal, Optional


OrderType = Literal["market", "limit"]
OrderSource = Literal[
    "submit_market_order",
    "submit_limit_order",
    "target_size",
    "target_value",
    "target_percent",
    "close_position",
    "close_portfolio",
    "cancel_order",
]
OrderSide = Literal["buy", "sell", "none"]
OrderStatus = Literal["pending", "filled", "canceled", "rejected", "skipped"]


@dataclass
class Order:
    id: str
    symbol: str
    portfolio: str
    order_type: OrderType
    source: OrderSource
    side: OrderSide
    qty: float
    status: OrderStatus
    requested_price: Optional[float] = None
    limit_price: Optional[float] = None
    filled_qty: float = 0.0
    avg_price: Optional[float] = None
    reason: Optional[str] = None
    created_dt: Any = None
    updated_dt: Any = None

    @property
    def is_done(self) -> bool:
        return self.status in ("filled", "canceled", "rejected", "skipped")
