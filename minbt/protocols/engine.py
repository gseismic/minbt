"""薄配置入口的输入和可选引擎契约，不包含调度或注册实现。"""

from typing import Any, Callable, Iterable, Mapping, Optional, Protocol, Type, runtime_checkable

from .broker import BrokerProtocol
from .data import DataFeedProtocol
from .result import ResultProtocol


Config = Mapping[str, Any]
FeedFactory = Callable[[Config], Iterable[DataFeedProtocol]]
BrokerFactory = Callable[[Config], BrokerProtocol]


@runtime_checkable
class EngineProtocol(Protocol):
    """显式注入的适配器驱动策略并冻结结果，不必须模拟 Exchange 的内部类型。"""

    def run(
        self,
        strategy_class: Type[Any],
        config: Config,
        *,
        feed_factory: FeedFactory,
        broker_factory: Optional[BrokerFactory] = None,
        control: Optional[Callable[[], str]] = None,
    ) -> ResultProtocol:
        ...


__all__ = ["Config", "FeedFactory", "BrokerFactory", "EngineProtocol"]
