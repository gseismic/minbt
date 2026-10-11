"""盈亏结果快照，统一账户汇总和单次记账的查询口径。"""

from dataclasses import dataclass
from math import fsum
from typing import Iterable, Literal, Optional

from .struct import DateType


PnlReason = Literal["trade", "liquidation", "bankruptcy", "bankruptcy_settlement"]


@dataclass(frozen=True)
class Pnl:
    """累计盈亏的不可变快照，避免查询结果被改写后影响账户统计。

    已实现和未实现盈亏均为毛盈亏；净盈亏扣除全部已付手续费，并包含穿仓结算调整。
    """

    realized_pnl: float = 0.0  # 累计平仓毛盈亏，沿用持仓的平均成本口径。
    unrealized_pnl: float = 0.0  # 当前持仓按最近一次估值计算的毛盈亏。
    fees: float = 0.0  # 累计实际扣除的手续费，包含开仓手续费。
    settlement_adjustment: float = 0.0  # 穿仓清零调整，用于对齐实际结算权益。

    @property
    def net_pnl(self) -> float:
        """返回已实现与未实现盈亏扣费、结算后的净盈亏。"""
        return fsum((self.realized_pnl, self.unrealized_pnl, -self.fees, self.settlement_adjustment))


@dataclass(frozen=True)
class PnlRecord:
    """一次实际成交或风险结算的不可变记录，供用户核对订单和累计盈亏。

    开仓、部分平仓和反手各记一条，不配对往返交易；系统结算没有普通订单 ID。
    """

    portfolio: str  # 记账所属分仓，关闭分仓后仍保留原归属。
    symbol: Optional[str]  # 标的；全仓清零的账户调整没有标的归属。
    qty: float  # 有符号成交数量；账户层面的结算调整为零。
    price: Optional[float]  # 成交或清仓估值价格；账户调整没有价格。
    realized_pnl: float  # 本次记账实现的毛盈亏。
    fees: float  # 本次实际扣除的手续费，不分摊过去的开仓手续费。
    settlement_adjustment: float = 0.0  # 本次穿仓结算的权益调整。
    order_id: Optional[str] = None  # 关联已成交订单；系统结算为 None。
    reason: PnlReason = "trade"  # 普通成交、强平、穿仓或账户清零调整。
    dt: Optional[DateType] = None  # 本次成交或风险结算的行情时间，可缺省。

    @property
    def net_pnl(self) -> float:
        """返回本次记账对累计已结算净盈亏的贡献。"""
        return fsum((self.realized_pnl, -self.fees, self.settlement_adjustment))


def _sum_pnl(results: Iterable[Pnl]) -> Pnl:
    """汇总已有快照，不回放订单或改动持仓。"""
    results = list(results)
    return Pnl(
        realized_pnl=fsum(result.realized_pnl for result in results),
        unrealized_pnl=fsum(result.unrealized_pnl for result in results),
        fees=fsum(result.fees for result in results),
        settlement_adjustment=fsum(result.settlement_adjustment for result in results),
    )
