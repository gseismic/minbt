from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class FeedEvent:
    event_type: str
    dt: datetime
    data: object
    prices: Mapping[str, float] = None


@runtime_checkable
class DataFeedProtocol(Protocol):
    name: str
    event_type: str

    def events(self) -> Iterable[FeedEvent]:
        ...
