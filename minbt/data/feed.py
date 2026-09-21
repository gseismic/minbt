"""历史数据 Feed 的最小契约。"""

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from .model import MarketEvent


@runtime_checkable
class DataFeedProtocol(Protocol):
    """Exchange 接受的有限历史 Feed。

    Feed 只负责读取数据，不负责解释估值价格。最小实现只需要 `name` 和 `events()`；
    回放能力属性是可选的优化声明，缺省由 Exchange 采用安全值。`events()` 每次运行都应
    返回一条新的、最终会结束的事件序列。
    """

    name: str

    def events(self) -> Iterable[MarketEvent]:
        ...


class SimpleFeed:
    """低门槛的历史 Feed 基类。

    子类通常只需要设置 `name` 并实现 `events()`。默认选择安全的全量预加载路径；
    已知有序且可渐进读取的来源可以覆盖能力属性。
    """

    supports_preload = True
    supports_incremental = False
    ordered = False
    replayable = True

    def __init__(self, name: str, *, feed_priority: int = 0):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("feed name must be a non-empty string")
        if isinstance(feed_priority, bool) or not isinstance(feed_priority, int):
            raise TypeError("feed_priority must be an integer")
        self.name = name
        self.feed_priority = feed_priority

    def prepare(self) -> None:
        return None

    def events(self) -> Iterable[MarketEvent]:
        raise NotImplementedError

    def close(self) -> None:
        return None


class MemoryFeed(SimpleFeed):
    """Exchange.set_* 使用的内存 Feed。"""

    supports_preload = True
    supports_incremental = True
    ordered = True
    replayable = True

    def __init__(self, name: str, events, *, feed_priority: int = 0):
        super().__init__(name, feed_priority=feed_priority)
        self.supports_incremental = True
        self.ordered = True
        self._events = tuple(events)

    def events(self):
        return iter(self._events)


__all__ = ["DataFeedProtocol", "SimpleFeed", "MemoryFeed"]
