"""历史行情回放 Exchange。

Exchange 只负责读取、排序、分批和分发市场数据；估值价格由 Broker 选择。
"""

from collections import OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
import heapq
import sys
import time
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import polars as pl

from .data.feed import MemoryFeed
from .data.model import Bar, MarketEvent, News, datetime_key, normalize_datetime
from .data.replay import BatchItem, TimeBatch
from .logger import logger as default_logger
from .strategy import Strategy


_KLINE = "kline"
_ORDERBOOK = "orderbook"
_TRADE = "trade"
_CUSTOM = "custom"
_NEWS = "news"


@dataclass
class _Source:
    feed: Any
    name: str
    feed_priority: int
    registration_index: int


class _Cursor:
    """Exchange 内部 Cursor 包装，统一来源属性和生命周期。"""

    def __init__(self, source: _Source):
        self.source = source
        feed = source.feed
        self.name = source.name
        self.feed_priority = source.feed_priority
        self.registration_index = source.registration_index
        self.supports_preload = Exchange._feed_capability(feed, "supports_preload")
        self.supports_incremental = Exchange._feed_capability(feed, "supports_incremental")
        self.ordered = Exchange._feed_capability(feed, "ordered")
        self.replayable = Exchange._feed_capability(feed, "replayable")

    def prepare(self) -> None:
        prepare = getattr(self.source.feed, "prepare", None)
        if callable(prepare):
            prepare()

    def events(self) -> Iterable[MarketEvent]:
        return self.source.feed.events()

    def close(self) -> None:
        close = getattr(self.source.feed, "close", None)
        if callable(close):
            close()


class Exchange:
    """最小历史回放 Exchange。"""

    _FAMILY_ORDER = {_KLINE: 0, _ORDERBOOK: 1, _TRADE: 2, _CUSTOM: 3, _NEWS: 4}
    _CALLBACKS = {
        _KLINE: "on_bars",
        _ORDERBOOK: "on_books",
        _TRADE: "on_trades",
        _NEWS: "on_news",
    }
    _FEED_DEFAULTS = {
        "supports_preload": True,
        "supports_incremental": False,
        "ordered": False,
        "replayable": True,
    }

    def __init__(self, logger=None):
        self.strategies = OrderedDict()
        self.logger = logger or default_logger
        self._sources: Dict[str, _Source] = OrderedDict()
        self._managed_memory_sources = set()
        self._current_dt: Optional[datetime] = None
        self._run_count = 0

    # --------------------------- public data entry points ---------------------------

    def set_bars(
        self,
        data: Union[pd.DataFrame, pl.DataFrame, List[Dict]],
        *,
        date_key: str = "dt",
        symbol_key: str = "symbol",
        feed_priority: int = 0,
    ) -> None:
        self._set_bar_rows(
            "bars",
            _KLINE,
            data,
            date_key=date_key,
            symbol_key=symbol_key,
            feed_priority=feed_priority,
            unique_symbol_at_dt=True,
        )

    def set_books(
        self,
        data: Union[pd.DataFrame, pl.DataFrame, List[Dict]],
        *,
        date_key: str = "dt",
        symbol_key: str = "symbol",
        feed_priority: int = 0,
    ) -> None:
        self._set_bar_rows(
            "books",
            _ORDERBOOK,
            data,
            date_key=date_key,
            symbol_key=symbol_key,
            feed_priority=feed_priority,
            unique_symbol_at_dt=True,
        )

    def set_trades(
        self,
        data: Union[pd.DataFrame, pl.DataFrame, List[Dict]],
        *,
        date_key: str = "dt",
        symbol_key: str = "symbol",
        feed_priority: int = 0,
    ) -> None:
        self._set_bar_rows(
            "trades",
            _TRADE,
            data,
            date_key=date_key,
            symbol_key=symbol_key,
            feed_priority=feed_priority,
            unique_symbol_at_dt=False,
        )

    def set_news(
        self,
        data: Union[pd.DataFrame, pl.DataFrame, List[Dict]],
        *,
        date_key: str = "dt",
        symbol_key: str = "symbol",
        feed_priority: int = 0,
    ) -> None:
        rows = self._to_rows(data)
        events = []
        for row_index, row in enumerate(rows):
            if date_key not in row:
                raise ValueError(f"news data missing required column: {date_key!r}")
            dt = normalize_datetime(row[date_key])
            symbol = row.get(symbol_key)
            payload = {
                key: value
                for key, value in row.items()
                if key not in {date_key, "dt", symbol_key, "symbol"}
            }
            events.append((datetime_key(dt), row_index, News(dt=dt, data=payload, symbol=symbol)))
        events.sort(key=lambda item: (item[0], item[1]))
        self._replace_source(
            MemoryFeed(
                "news",
                (event for _, _, event in events),
                feed_priority=self._validate_priority(feed_priority),
            )
        )

    def add_feed(self, feed, *, feed_priority: Optional[int] = None) -> None:
        name = getattr(feed, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise TypeError("feed.name must be a non-empty string")
        if not callable(getattr(feed, "events", None)):
            raise TypeError("feed must provide events()")
        if getattr(feed, "is_live", False):
            raise ValueError("Exchange only accepts finite historical feeds; use a realtime entry later")
        priority = getattr(feed, "feed_priority", 0) if feed_priority is None else feed_priority
        priority = self._validate_priority(priority)
        capabilities = {
            attr: self._feed_capability(feed, attr)
            for attr in self._FEED_DEFAULTS
        }
        for attr, value in capabilities.items():
            if not isinstance(getattr(feed, attr, value), bool):
                raise TypeError(f"feed.{attr} must be bool")
        if not (capabilities["supports_preload"] or capabilities["supports_incremental"]):
            raise ValueError(f"feed {name!r} supports neither preload nor incremental replay")
        if name in self._sources:
            raise ValueError(f"feed name already exists: {name!r}")
        self._sources[name] = _Source(
            feed=feed,
            name=name,
            feed_priority=priority,
            registration_index=len(self._sources),
        )

    def add_strategy(self, strategy: Strategy) -> None:
        if not hasattr(strategy, "strategy_id"):
            raise TypeError("strategy must have strategy_id")
        required = ("on_init", "on_bar", "on_bars", "on_books", "on_trades", "on_news", "on_finish")
        for method in required:
            if not callable(getattr(strategy, method, None)):
                raise TypeError(f"strategy must provide {method}()")
        if strategy.strategy_id in self.strategies:
            raise ValueError(f"strategy id already exists: {strategy.strategy_id!r}")
        strategy.set_exchange(self)
        self.strategies[strategy.strategy_id] = strategy

    def remove_strategy(self, strategy_id: str) -> None:
        del self.strategies[strategy_id]

    def get_current_dt(self) -> Optional[datetime]:
        return self._current_dt

    # --------------------------- run modes ---------------------------

    def run(self, *, load_mode: str = "auto") -> None:
        if not self._sources:
            raise ValueError("Exchange data is not set; call set_bars() or add_feed() first")
        if load_mode not in {"auto", "preload", "incremental"}:
            raise ValueError("load_mode must be 'auto', 'preload', or 'incremental'")
        if self._run_count and any(
            not self._feed_capability(source.feed, "replayable") for source in self._sources.values()
        ):
            names = [
                source.name
                for source in self._sources.values()
                if not self._feed_capability(source.feed, "replayable")
            ]
            raise RuntimeError(f"non-replayable feeds cannot be run again: {names!r}")

        mode = self._choose_load_mode(load_mode)
        cursors = [_Cursor(source) for source in self._sources.values()]
        self._current_dt = None
        self._run_count += 1
        start_time = time.time()
        step = 0
        try:
            for cursor in cursors:
                cursor.prepare()
            self.logger.info(
                f"Start running {len(self.strategies)} strategies "
                f"(load_mode={mode}, feeds={len(cursors)})..."
            )
            for strategy in self.strategies.values():
                strategy.on_init()
            batches = self._iter_preload_batches(cursors) if mode == "preload" else self._iter_incremental_batches(cursors)
            for batch in batches:
                self._current_dt = batch.dt
                for broker in self._unique_brokers():
                    broker.process_market_batch(batch)
                self._dispatch_batch(batch)
                for strategy in self.strategies.values():
                    strategy._record_broker_history()
                step += 1

            for strategy in self.strategies.values():
                strategy.on_finish()
            elapsed = time.time() - start_time
            self.logger.info(f"All strategies completed, total time: {elapsed:.2f}s")
            self.logger.info(f"{elapsed / step:.2f}s/step" if step else "0 steps")
        finally:
            self._close_resources(cursors, label="feed")

    def _choose_load_mode(self, requested: str) -> str:
        sources = list(self._sources.values())
        if requested == "auto":
            if all(
                self._feed_capability(source.feed, "supports_incremental")
                and self._feed_capability(source.feed, "ordered")
                for source in sources
            ):
                return "incremental"
            if all(self._feed_capability(source.feed, "supports_preload") for source in sources):
                return "preload"
            raise ValueError(self._mode_error("auto"))
        if requested == "incremental" and not all(
            self._feed_capability(source.feed, "supports_incremental")
            and self._feed_capability(source.feed, "ordered")
            for source in sources
        ):
            raise ValueError(self._mode_error(requested))
        if requested == "preload" and not all(
            self._feed_capability(source.feed, "supports_preload") for source in sources
        ):
            raise ValueError(self._mode_error(requested))
        return requested

    @classmethod
    def _feed_capability(cls, feed, name: str) -> bool:
        """读取 Feed 能力；简单 Feed 缺省采用安全声明。"""

        return getattr(feed, name, cls._FEED_DEFAULTS[name])

    def _mode_error(self, requested: str) -> str:
        capabilities = {
            source.name: {
                "preload": self._feed_capability(source.feed, "supports_preload"),
                "incremental": self._feed_capability(source.feed, "supports_incremental"),
                "ordered": self._feed_capability(source.feed, "ordered"),
            }
            for source in self._sources.values()
        }
        return f"load_mode={requested!r} is unavailable; feed capabilities: {capabilities!r}"

    # --------------------------- cursor merge ---------------------------

    def _iter_preload_batches(self, cursors: List[_Cursor]):
        entries = []
        for cursor in cursors:
            source_entries = []
            iterator = iter(cursor.events())
            try:
                for sequence, event in enumerate(self._checked_events(cursor, iterator)):
                    source_entries.append((cursor, sequence, event))
            finally:
                self._close_resources([cursor, iterator], label=f"preload source {cursor.name}")
            if not cursor.ordered:
                source_entries.sort(key=lambda item: (datetime_key(item[2].dt), item[1]))
            entries.extend(source_entries)
        entries.sort(key=lambda item: (datetime_key(item[2].dt), item[0].registration_index, item[1]))
        yield from self._batches_from_entries(entries)

    def _iter_incremental_batches(self, cursors: List[_Cursor]):
        iterators = []
        heap = []
        previous_by_cursor = {}
        try:
            for cursor_index, cursor in enumerate(cursors):
                iterator = iter(cursor.events())
                iterators.append(iterator)
                event = self._next_checked_incremental(
                    cursor,
                    iterator,
                    cursor_index,
                    previous_by_cursor,
                )
                if event is not None:
                    heapq.heappush(
                        heap,
                        (
                            datetime_key(event.dt),
                            cursor.registration_index,
                            0,
                            cursor_index,
                            event,
                        ),
                    )
            while heap:
                current_key = heap[0][0]
                entries = []
                while heap and heap[0][0] == current_key:
                    _, _, sequence, cursor_index, event = heapq.heappop(heap)
                    cursor = cursors[cursor_index]
                    entries.append((cursor, sequence, event))
                    next_sequence = sequence + 1
                    next_event = self._next_checked_incremental(
                        cursor,
                        iterators[cursor_index],
                        cursor_index,
                        previous_by_cursor,
                    )
                    if next_event is not None:
                        heapq.heappush(
                            heap,
                            (
                                datetime_key(next_event.dt),
                                cursor.registration_index,
                                next_sequence,
                                cursor_index,
                                next_event,
                            ),
                        )
                yield self._make_batch(entries)
        finally:
            self._close_resources(iterators, label="event iterator")

    def _close_resources(self, resources, *, label: str) -> None:
        """关闭资源；有业务异常时不让关闭异常覆盖原始异常。"""

        active_exception = sys.exc_info()[1]
        close_errors = []
        for resource in reversed(resources):
            close = getattr(resource, "close", None)
            if not callable(close):
                continue
            try:
                close()
            except Exception as exc:
                if active_exception is None:
                    close_errors.append(exc)
                else:
                    self.logger.exception("failed to close %s", label)
        if close_errors:
            raise close_errors[0]

    def _next_checked_incremental(self, cursor, iterator, cursor_index, previous_by_cursor):
        try:
            event = next(iterator)
        except StopIteration:
            return None
        self._validate_event(cursor, event)
        current_key = datetime_key(event.dt)
        previous = previous_by_cursor.get(cursor_index)
        if previous is not None and current_key < previous["key"]:
            raise ValueError(
                f"cursor {cursor.name!r} is not ordered by dt: "
                f"{event.dt!r} came after {previous['dt']!r}"
            )
        previous_by_cursor[cursor_index] = {"key": current_key, "dt": event.dt}
        return event

    def _checked_events(self, cursor: _Cursor, events=None):
        previous_key = None
        previous_dt = None
        for event in cursor.events() if events is None else events:
            self._validate_event(cursor, event)
            current_key = datetime_key(event.dt)
            if cursor.ordered and previous_key is not None and current_key < previous_key:
                raise ValueError(
                    f"cursor {cursor.name!r} is not ordered by dt: "
                    f"{event.dt!r} came after {previous_dt!r}"
                )
            previous_key = current_key
            previous_dt = event.dt
            yield event

    def _validate_event(self, cursor: _Cursor, event: Any) -> None:
        if not isinstance(event, (Bar, News)):
            raise TypeError(
                f"feed {cursor.name!r} must yield Bar or News, got {type(event).__name__}"
            )
        if not isinstance(event.dt, datetime):
            raise TypeError(f"feed {cursor.name!r} event dt must be datetime")

    def _batches_from_entries(self, entries):
        current = []
        current_key = None
        for entry in entries:
            key = datetime_key(entry[2].dt)
            if current_key is None:
                current_key = key
            elif key != current_key:
                yield self._make_batch(current)
                current = []
                current_key = key
            current.append(entry)
        if current:
            yield self._make_batch(current)

    def _make_batch(self, entries) -> TimeBatch:
        items = [
            BatchItem(
                feed_name=cursor.name,
                feed_priority=cursor.feed_priority,
                registration_index=cursor.registration_index,
                sequence=sequence,
                event=event,
            )
            for cursor, sequence, event in entries
        ]
        items.sort(key=self._item_sort_key)
        self._warn_same_priority_overlap(items)
        self._validate_batch_duplicates(items)
        return TimeBatch(dt=items[0].dt, items=tuple(items))

    def _item_sort_key(self, item: BatchItem):
        return (
            self._family_rank(item.event),
            -item.feed_priority,
            item.registration_index,
            item.sequence,
        )

    def _family_rank(self, event: MarketEvent) -> int:
        if isinstance(event, News):
            return self._FAMILY_ORDER[_NEWS]
        return self._FAMILY_ORDER.get(event.kind, self._FAMILY_ORDER[_CUSTOM])

    def _validate_batch_duplicates(self, items: List[BatchItem]) -> None:
        seen = set()
        for item in items:
            event = item.event
            if not isinstance(event, Bar) or event.kind not in {_KLINE, _ORDERBOOK}:
                continue
            key = (item.feed_name, event.kind, event.symbol)
            if key in seen:
                raise ValueError(
                    f"feed {item.feed_name!r} contains duplicate "
                    f"({item.dt!r}, {event.symbol!r}, {event.kind!r}) bars"
                )
            seen.add(key)

    def _warn_same_priority_overlap(self, items: List[BatchItem]) -> None:
        seen = {}
        warned = set()
        for item in items:
            event = item.event
            if isinstance(event, News):
                continue
            family = event.kind
            key = (family, event.symbol)
            previous = seen.get(key, [])
            for old in previous:
                if old.feed_name == item.feed_name or old.feed_priority != item.feed_priority:
                    continue
                pair = tuple(sorted((old.feed_name, item.feed_name))) + key
                if pair not in warned:
                    self.logger.warning(
                        "same-priority feed overlap at dt=%s, family=%s, symbol=%s: %s and %s; "
                        "registration order is used",
                        item.dt,
                        family,
                        event.symbol,
                        old.feed_name,
                        item.feed_name,
                    )
                    warned.add(pair)
            previous.append(item)
            seen[key] = previous

    # --------------------------- callback projection ---------------------------

    def _dispatch_batch(self, batch: TimeBatch) -> None:
        groups = OrderedDict()
        for item in batch.items:
            callback = self._callback_for(item.event)
            if callback is None:
                continue
            key = (callback, item.feed_name, item.feed_priority, item.registration_index)
            groups.setdefault(key, []).append(item)

        for key, items in groups.items():
            callback = key[0]
            if callback == "on_bar":
                for item in items:
                    for strategy in self.strategies.values():
                        strategy._dispatch_exchange_callback(callback, batch.dt, item.event)
                continue
            payload = self._callback_payload(callback, items)
            for strategy in self.strategies.values():
                strategy._dispatch_exchange_callback(callback, batch.dt, payload)

    def _callback_for(self, event: MarketEvent) -> Optional[str]:
        if isinstance(event, News):
            return "on_news"
        return self._CALLBACKS.get(event.kind, "on_bar")

    def _callback_payload(self, callback: str, items: List[BatchItem]):
        if callback in {"on_bars", "on_books"}:
            payload = OrderedDict()
            for item in items:
                event = item.event
                if event.symbol in payload:
                    raise ValueError(
                        f"duplicate {callback} symbol {event.symbol!r} in feed {item.feed_name!r}"
                    )
                payload[event.symbol] = event.data
            return payload
        if callback == "on_trades":
            payload = OrderedDict()
            for item in items:
                event = item.event
                payload.setdefault(event.symbol, []).append(event.data)
            return payload
        if callback == "on_news":
            return tuple(item.event for item in items)
        raise ValueError(f"unsupported strategy callback: {callback!r}")

    # --------------------------- row normalization ---------------------------

    def _set_bar_rows(
        self,
        source_name: str,
        kind: str,
        data,
        *,
        date_key: str,
        symbol_key: str,
        feed_priority: int,
        unique_symbol_at_dt: bool,
    ) -> None:
        rows = self._to_rows(data)
        events = []
        seen = set()
        priority = self._validate_priority(feed_priority)
        for row_index, row in enumerate(rows):
            for key in (date_key, symbol_key):
                if key not in row:
                    raise ValueError(f"{source_name} data missing required column: {key!r}")
            dt = normalize_datetime(row[date_key])
            if row[symbol_key] is None:
                raise ValueError(f"{source_name} symbol must not be None")
            symbol = str(row[symbol_key]).strip().upper()
            if not symbol:
                raise ValueError(f"{source_name} symbol must not be empty")
            if unique_symbol_at_dt:
                duplicate_key = (datetime_key(dt), symbol)
                if duplicate_key in seen:
                    raise ValueError(
                        f"{source_name} data contains duplicate ({dt!r}, {symbol!r}) rows"
                    )
                seen.add(duplicate_key)
            payload = {
                key: value
                for key, value in row.items()
                if key not in {date_key, "dt", symbol_key, "symbol"}
            }
            events.append((datetime_key(dt), row_index, Bar(dt=dt, symbol=symbol, kind=kind, data=payload)))
        events.sort(key=lambda item: (item[0], item[1]))
        self._replace_source(
            MemoryFeed(
                source_name,
                (event for _, _, event in events),
                feed_priority=priority,
            )
        )

    def _replace_source(self, feed) -> None:
        name = feed.name
        if name in self._sources and name not in self._managed_memory_sources:
            raise ValueError(f"feed name already exists and cannot be replaced by set_*(): {name!r}")
        self._sources[name] = _Source(
            feed=feed,
            name=name,
            feed_priority=feed.feed_priority,
            registration_index=(
                self._sources[name].registration_index if name in self._sources else len(self._sources)
            ),
        )
        self._managed_memory_sources.add(name)

    @staticmethod
    def _validate_priority(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("feed_priority must be an integer")
        return value

    @staticmethod
    def _to_rows(data) -> List[dict]:
        if isinstance(data, pd.DataFrame):
            rows = data.to_dict(orient="records")
        elif isinstance(data, pl.DataFrame):
            rows = data.to_dicts()
        elif hasattr(data, "to_dict"):
            try:
                rows = data.to_dict(orient="records")
            except TypeError:
                rows = data.to_dict()
        else:
            rows = data
        if rows is None:
            return []
        if isinstance(rows, Mapping):
            raise TypeError("data must be a row sequence, not a single mapping")
        try:
            return [dict(row) for row in rows]
        except (TypeError, ValueError) as exc:
            raise TypeError("data must be an iterable of row mappings") from exc

    # --------------------------- broker helpers ---------------------------

    def _unique_brokers(self):
        seen = set()
        for strategy in self.strategies.values():
            broker = getattr(strategy, "broker", None)
            if broker is None or id(broker) in seen:
                continue
            seen.add(id(broker))
            yield broker


__all__ = ["Exchange"]
