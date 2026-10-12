"""运行结果的数据快照，供绘图与比较独立实验使用。"""

from dataclasses import dataclass, fields
from datetime import datetime
import copy
import math
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .broker import Pnl
from .data.model import _freeze_payload, normalize_symbol
from .protocols.result import OrderProtocol, OrderSnapshot, PnlProtocol


@dataclass(frozen=True)
class _AccountSnapshot:
    """冻结同一账户的数据，让共享账户的策略查询同一个结果。"""

    initial_cash: Optional[float]  # None 表示自定义账户未提供该能力。
    equity: Tuple[Tuple[datetime, float], ...]  # 每个完整批次的账户权益。
    positions: Tuple[Mapping[str, float], ...]  # 与权益时间对齐的 main 持仓。
    final_positions: Mapping[str, Mapping[str, float]]  # 最终各分仓持仓。
    all_portfolios: bool  # 自定义账户可能仅能提供默认分仓。
    orders: Optional[Tuple[OrderSnapshot, ...]]  # None 表示不支持订单快照。
    pnl: Optional[Pnl]  # None 表示不支持盈亏汇总。


def _optional_query(broker, name):
    """可选数据能力可以缺失或声明未实现，真正的查询故障仍然传播。"""

    method = getattr(broker, name, None)
    if not callable(method):
        return False, None
    try:
        return True, method()
    except NotImplementedError:
        return False, None


def _snapshot_account(broker, initial_cash, equity, positions) -> _AccountSnapshot:
    """只读取账户能力，冻结已有数据，不扩充自定义 Broker 的必需协议。"""

    all_portfolios, names = _optional_query(broker, "get_portfolios")
    if not all_portfolios:
        names = ("main",)
    final_positions = MappingProxyType({
        name: MappingProxyType(dict(
            broker.get_position_sizes(portfolio=name) if all_portfolios else broker.get_position_sizes()
        ))
        for name in names
    })
    has_orders, raw_orders = _optional_query(broker, "get_orders")
    orders = None
    if has_orders:
        copied_orders = []
        for order in raw_orders:
            if not isinstance(order, OrderProtocol):
                raise TypeError("get_orders() must return records with the standard Order fields")
            copied_orders.append(OrderSnapshot(**{
                field.name: _freeze_payload(copy.deepcopy(getattr(order, field.name)))
                for field in fields(OrderSnapshot)
            }))
        orders = tuple(copied_orders)
    has_pnl, pnl = _optional_query(broker, "get_total_pnl")
    if has_pnl:
        if not isinstance(pnl, PnlProtocol):
            raise TypeError("get_total_pnl() must provide the standard Pnl fields and net_pnl")
        # 自定义记录可能可变；转换为原公共 Pnl，结果不持有插件的活引用。
        raw_pnl = pnl
        pnl = Pnl(**{
            field.name: copy.deepcopy(getattr(pnl, field.name))
            for field in fields(Pnl)
        })
        if not math.isfinite(pnl.net_pnl) or not math.isclose(pnl.net_pnl, raw_pnl.net_pnl):
            raise ValueError("get_total_pnl() must agree with the finite standard Pnl components")
    return _AccountSnapshot(
        initial_cash=initial_cash,
        equity=tuple(equity),
        positions=tuple(MappingProxyType(dict(row)) for row in positions),
        final_positions=final_positions,
        all_portfolios=all_portfolios,
        orders=orders,
        pnl=pnl,
    )


@dataclass(frozen=True)
class RunResult:
    """独立的运行结果，仅持有数据，旧实验不受后续账户操作影响。"""

    meta: Mapping[str, Any]  # 结束状态、实际进度和不可变控制记录。
    _accounts: Mapping[str, Optional[_AccountSnapshot]]  # 策略 ID 到账户快照的别名。

    def _account(self, strategy_id) -> _AccountSnapshot:
        if strategy_id is None:
            if len(self._accounts) != 1:
                raise ValueError("strategy_id is required for multiple strategies")
            strategy_id = next(iter(self._accounts))
        if strategy_id not in self._accounts:
            raise ValueError(f"unknown strategy_id: {strategy_id!r}")
        account = self._accounts[strategy_id]
        if account is None:
            raise ValueError(f"strategy {strategy_id!r} has no Broker")
        return account

    def get_initial_cash(self, *, strategy_id=None) -> float:
        value = self._account(strategy_id).initial_cash
        if value is None:
            raise NotImplementedError("Broker does not provide initial_cash")
        return value

    def get_equity_curve(self, *, strategy_id=None) -> List[Tuple[datetime, float]]:
        return list(self._account(strategy_id).equity)

    def get_position_curve(self, symbol: str, *, strategy_id=None) -> List[Tuple[datetime, float]]:
        symbol = normalize_symbol(symbol)
        account = self._account(strategy_id)
        return [(dt, row.get(symbol, 0.0)) for (dt, _), row in zip(account.equity, account.positions)]

    def get_orders(self, *, strategy_id=None) -> List[OrderSnapshot]:
        value = self._account(strategy_id).orders
        if value is None:
            raise NotImplementedError("Broker does not provide get_orders()")
        return list(value)

    def get_total_pnl(self, *, strategy_id=None) -> Pnl:
        value = self._account(strategy_id).pnl
        if value is None:
            raise NotImplementedError("Broker does not provide get_total_pnl()")
        return value

    def get_position_sizes(self, *, strategy_id=None, portfolio=None) -> Dict[str, float]:
        account = self._account(strategy_id)
        name = "main" if portfolio is None else portfolio
        if name not in account.final_positions:
            if not account.all_portfolios:
                raise NotImplementedError("Broker does not provide named portfolio snapshots")
            raise ValueError(f"portfolio not found: {name}")
        return dict(account.final_positions[name])


__all__ = ["RunResult"]
