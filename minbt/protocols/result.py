"""结果字段与查询契约，供独立绘图和自定义交易实现共用。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class OrderProtocol(Protocol):
    """既有订单的标准字段，不强制插件返回内置 Order 类。"""

    id: str  # 原订单标识。
    symbol: str  # 原交易标的。
    portfolio: str  # 所属分仓。
    order_type: str  # 订单类型。
    source: str  # 原交易入口。
    side: str  # 买卖方向。
    qty: float  # 有符号请求数量。
    status: str  # 当前订单状态。
    requested_price: Optional[float]  # 显式请求价格。
    limit_price: Optional[float]  # 限价阈值。
    filled_qty: float  # 实际成交数量。
    avg_price: Optional[float]  # 实际平均成交价格。
    reason: Optional[str]  # 业务原因。
    created_dt: Any  # 创建时间，兼容原载荷类型。
    updated_dt: Any  # 最后更新时间。


@dataclass(frozen=True)
class OrderSnapshot:
    """冻结原订单字段，独立于任何交易实现及活句柄。"""

    id: str  # 原订单 ID。
    symbol: str  # 交易标的。
    portfolio: str  # 所属分仓。
    order_type: str  # 市价或限价订单。
    source: str  # 创建订单的交易接口。
    side: str  # 买入、卖出或无交易方向。
    qty: float  # 有符号的请求数量。
    status: str  # 实际结束点的订单状态。
    requested_price: Optional[float] = None  # 请求成交价。
    limit_price: Optional[float] = None  # 限价阈值。
    filled_qty: float = 0.0  # 已实际成交数量。
    avg_price: Optional[float] = None  # 平均成交价。
    reason: Optional[str] = None  # 业务原因说明。
    created_dt: Any = None  # 创建时间，不暴露活订单引用。
    updated_dt: Any = None  # 最后一次状态更新时间。


@runtime_checkable
class PnlProtocol(Protocol):
    """当前四项盈亏口径，不给扩展账本添加新的强制财务字段。"""

    @property
    def realized_pnl(self) -> float: ...
    @property
    def unrealized_pnl(self) -> float: ...
    @property
    def fees(self) -> float: ...
    @property
    def settlement_adjustment(self) -> float: ...
    @property
    def net_pnl(self) -> float: ...


@runtime_checkable
class ResultProtocol(Protocol):
    """沿用 RunResult 查询；实现负责返回独立快照，缺失能力明确报错。"""

    meta: Mapping[str, Any]  # 同次实验的状态、真实进度和控制信息。

    def get_initial_cash(self, *, strategy_id=None) -> float: ...
    def get_equity_curve(self, *, strategy_id=None) -> List[Tuple[datetime, float]]: ...
    def get_position_curve(self, symbol: str, *, strategy_id=None) -> List[Tuple[datetime, float]]: ...
    def get_orders(self, *, strategy_id=None) -> List[OrderSnapshot]: ...
    def get_total_pnl(self, *, strategy_id=None) -> PnlProtocol: ...
    def get_position_sizes(self, *, strategy_id=None, portfolio=None) -> Dict[str, float]: ...


__all__ = ["OrderProtocol", "OrderSnapshot", "PnlProtocol", "ResultProtocol"]
