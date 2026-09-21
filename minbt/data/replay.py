"""Exchange 使用的内部历史回放结构。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, Protocol, Tuple, runtime_checkable

from .model import Bar, MarketEvent, News


@runtime_checkable
class ReplayCursor(Protocol):
    """有限历史数据的内部读取契约。"""

    name: str
    feed_priority: int
    supports_preload: bool
    supports_incremental: bool
    ordered: bool
    replayable: bool

    def prepare(self) -> None:
        ...

    def events(self) -> Iterable[MarketEvent]:
        ...

    def close(self) -> None:
        ...


@dataclass(frozen=True)
class BatchItem:
    """TimeBatch 中的一条事件及其来源元信息。"""

    feed_name: str
    feed_priority: int
    registration_index: int
    sequence: int
    event: MarketEvent

    @property
    def dt(self) -> datetime:
        return self.event.dt


@dataclass(frozen=True)
class TimeBatch:
    """同一时间点收齐后的原始事件集合。"""

    dt: datetime
    items: Tuple[BatchItem, ...]

    def __post_init__(self) -> None:
        if any(item.dt != self.dt for item in self.items):
            raise ValueError("all TimeBatch items must have the same dt")

    def bars(self, *, kind: Optional[str] = None) -> Tuple[BatchItem, ...]:
        """返回批次中的 Bar，可按 kind 过滤。"""

        return tuple(
            item
            for item in self.items
            if isinstance(item.event, Bar) and (kind is None or item.event.kind == kind)
        )

    def news(self) -> Tuple[BatchItem, ...]:
        return tuple(item for item in self.items if isinstance(item.event, News))


__all__ = ["ReplayCursor", "BatchItem", "TimeBatch"]
