"""数据形状与最小 Feed 契约；记录实例仍使用既有 Bar、News 和 TimeBatch。"""

from datetime import datetime
from typing import Any, Iterable, Optional, Protocol, Tuple, Union, runtime_checkable


class BarProtocol(Protocol):
    """描述既有 Bar 的只读字段，不新增解析或市场推断。"""

    @property
    def dt(self) -> datetime: ...
    @property
    def symbol(self) -> str: ...
    @property
    def kind(self) -> str: ...
    @property
    def data(self) -> Any: ...


class NewsProtocol(Protocol):
    """描述 News 的字段，允许没有关联标的。"""

    @property
    def dt(self) -> datetime: ...
    @property
    def symbol(self) -> Optional[str]: ...
    @property
    def data(self) -> Any: ...


MarketEvent = Union[BarProtocol, NewsProtocol]


@runtime_checkable
class DataFeedProtocol(Protocol):
    """有限历史读取器只需名称与事件迭代；排序及资源能力沿用可选约定。"""

    name: str  # 同次运行中唯一的来源名称。

    def events(self) -> Iterable[MarketEvent]: ...


class BatchItem(Protocol):
    """同一批次中已有事件的来源与排序信息。"""

    feed_name: str  # 来源名称，供当前价格配置匹配。
    feed_priority: int  # 原有来源优先级。
    registration_index: int  # 原有注册顺序。
    sequence: int  # 来源内顺序。
    event: MarketEvent  # 既有 Bar 或 News 记录。


class TimeBatch(Protocol):
    """回放 Broker 读取的批次形状，构造实现继续位于 minbt.data.replay。"""

    dt: datetime  # 所有事件共享的回放时间。
    items: Tuple[BatchItem, ...]  # 同时点收齐的原始事件及来源信息。

    def bars(self, *, kind: Optional[str] = None) -> Tuple[BatchItem, ...]: ...
    def news(self) -> Tuple[BatchItem, ...]: ...


__all__ = [
    "DataFeedProtocol", "BarProtocol", "NewsProtocol", "MarketEvent",
    "BatchItem", "TimeBatch",
]
