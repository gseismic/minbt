"""回测与实盘可低成本共用的最小策略接口。"""

from datetime import datetime
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class TradingBrokerProtocol(Protocol):
    """数量买正卖负；订单返回值由具体账户定义。"""

    def submit_market_order(self, symbol: str, qty: float) -> object: ...
    def get_position_size(self, symbol: str) -> float: ...


class StrategyExchangeProtocol(Protocol):
    """仅描述策略装配和时钟，不统一回放与实盘运行结果。"""

    def add_strategy(self, strategy) -> None: ...
    def get_current_dt(self) -> Optional[datetime]: ...
    def run(self) -> object: ...
