"""历史行情回放 Exchange。

Exchange 只负责读取、排序、分批和分发市场数据；估值价格由 Broker 选择。
"""

from collections import OrderedDict
from collections.abc import Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime
import heapq
import sys
import time
from threading import Lock, get_ident
from types import MappingProxyType
from typing import Any, Callable, Dict, Iterable, List, Optional, Union

import pandas as pd
import polars as pl

from .data.feed import MemoryFeed
from .data.model import Bar, MarketEvent, News, datetime_key, normalize_datetime
from .data.replay import BatchItem, TimeBatch
from .broker import Broker
from .logger import logger as default_logger
from .protocols.broker import ReplayBrokerProtocol
from .result import RunResult, _snapshot_account
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
        self._closed = False  # 预加载和运行收尾共用资源，避免重复关闭。

    def prepare(self) -> None:
        prepare = getattr(self.source.feed, "prepare", None)
        if callable(prepare):
            prepare()

    def events(self) -> Iterable[MarketEvent]:
        return self.source.feed.events()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
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
        self._strategies = OrderedDict()  # 注册只通过配置接口修改。
        self._strategies_view = MappingProxyType(self._strategies)  # 防止绕过运行归属校验。
        self.logger = logger or default_logger
        self._sources: Dict[str, _Source] = OrderedDict()
        self._managed_memory_sources = set()
        self._current_dt: Optional[datetime] = None
        self._run_state = "ready"  # 生命周期与策略是否接收行情独立。
        self._lifecycle_lock = Lock()  # 原子占用启动权，防止并发或递归重跑。

    @property
    def strategies(self):
        return self._strategies_view

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
        self._require_ready()
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
        with self._lifecycle_lock:
            self._require_ready()
            self._add_feed(feed, feed_priority=feed_priority)

    def _add_feed(self, feed, *, feed_priority) -> None:
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
        with self._lifecycle_lock:
            self._require_ready()
            if not hasattr(strategy, "strategy_id"):
                raise TypeError("strategy must have strategy_id")
            required = ("on_init", "on_bar", "on_bars", "on_books", "on_trades", "on_news", "on_finish")
            for method in required:
                if not callable(getattr(strategy, method, None)):
                    raise TypeError(f"strategy must provide {method}()")
            if strategy.strategy_id in self.strategies:
                raise ValueError(f"strategy id already exists: {strategy.strategy_id!r}")
            strategy.set_exchange(self)
            self._strategies[strategy.strategy_id] = strategy

    def remove_strategy(self, strategy_id: str) -> None:
        with self._lifecycle_lock:
            self._require_ready()
            strategy = self._strategies.pop(strategy_id)
            strategy.set_exchange(None)

    def get_current_dt(self) -> Optional[datetime]:
        return self._current_dt

    # --------------------------- run modes ---------------------------

    def run(
        self,
        *,
        start: Optional[Union[str, datetime]] = None,
        end: Optional[Union[str, datetime]] = None,
        control: Optional[Callable[[], str]] = None,
        load_mode: str = "auto",
    ) -> RunResult:
        """启动唯一一次运行；控制回调在完整时间批次前返回 continue/pause/exit。"""

        with self._lifecycle_lock:
            self._require_ready()
            if not self._sources:
                raise ValueError("Exchange data is not set; call set_bars() or add_feed() first")
            if not self.strategies:
                raise ValueError("Exchange has no strategies; call add_strategy() first")
            if control is not None and not callable(control):
                raise TypeError("control must be callable or None")
            if load_mode not in {"auto", "preload", "incremental"}:
                raise ValueError("load_mode must be 'auto', 'preload', or 'incremental'")
            start_dt = None if start is None else normalize_datetime(start)
            end_dt = None if end is None else normalize_datetime(end)
            if start_dt is not None and end_dt is not None and start_dt >= end_dt:
                raise ValueError("start must be earlier than end")
            mode = self._choose_load_mode(load_mode)
            cursors = [_Cursor(source) for source in self._sources.values()]
            brokers = list(self._unique_brokers())
            for broker in brokers:
                if not isinstance(broker, ReplayBrokerProtocol) or not callable(broker.process_market_batch):
                    raise TypeError("historical Exchange requires ReplayBrokerProtocol")
            self._claim_run(brokers)

        self._current_dt = None
        start_time = time.perf_counter()
        step = 0
        first_dt = last_dt = None
        control_state = "continue"
        control_events = []
        reason = "feed_exhausted"
        batches = None
        try:
            try:
                histories = {}
                for broker in brokers:
                    cash = getattr(broker, "initial_cash", None)
                    histories[id(broker)] = {
                        "initial_cash": None if cash is None else float(cash),
                        "equity": [], "positions": [],
                    }
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
                    if start_dt is not None and batch.dt < start_dt:
                        continue
                    if end_dt is not None and batch.dt >= end_dt:
                        reason = "end_reached"
                        break
                    with self._read_only_brokers(brokers, "control"):
                        action = "continue" if control is None else control()
                    if not isinstance(action, str) or action not in ("continue", "pause", "exit"):
                        raise ValueError("control must return 'continue', 'pause', or 'exit'")
                    if action != control_state:
                        control_events.append((last_dt, step, action))
                        control_state = action
                    if action == "exit":
                        reason = "control_exit"
                        break
                    self._current_dt = batch.dt
                    for broker in brokers:
                        broker.process_market_batch(batch)
                    if action == "continue":
                        self._dispatch_batch(batch)
                    for strategy in self.strategies.values():
                        strategy._record_broker_history()
                    for broker in brokers:
                        history = histories[id(broker)]
                        history["equity"].append((batch.dt, broker.get_total_equity()))
                        history["positions"].append(dict(broker.get_position_sizes()))
                    step += 1
                    first_dt = batch.dt if first_dt is None else first_dt
                    last_dt = batch.dt
                if not step and reason != "control_exit":
                    raise ValueError("no data in the requested run window")
                status = "exited" if reason == "control_exit" else "completed"
                snapshots = {
                    id(broker): _snapshot_account(broker, **histories[id(broker)])
                    for broker in brokers
                }
                result = RunResult(
                    meta=MappingProxyType({
                        "status": status, "reason": reason, "control_state": control_state,
                        "start": start_dt, "end": end_dt,
                        "first_dt": first_dt, "last_dt": last_dt, "step_count": step,
                        "strategy_ids": tuple(self.strategies),
                        "control_events": tuple(control_events),
                    }),
                    _accounts=MappingProxyType({
                        name: snapshots.get(id(strategy.broker))
                        for name, strategy in self.strategies.items()
                    }),
                )
                with self._read_only_brokers(brokers, "on_finish"):
                    for strategy in self.strategies.values():
                        strategy.on_finish()
            finally:
                self._close_resources([*cursors, batches], label="run resources")
            self._run_state = status
            elapsed = time.perf_counter() - start_time
            self.logger.info(f"Run {status} (reason={reason}), total time: {elapsed:.2f}s")
            self.logger.info(f"{elapsed / step:.2f}s/step" if step else "0 steps")
            return result
        except BaseException:
            self._run_state = "failed"
            raise

    def _require_ready(self) -> None:
        if self._run_state != "ready":
            raise RuntimeError(f"Exchange can only be run once (state={self._run_state})")

    def _claim_run(self, brokers) -> None:
        """一次性占用实例；共享 Broker 的占用检查跨 Exchange 也保持原子性。"""

        native_brokers = sorted((broker for broker in brokers if isinstance(broker, Broker)), key=id)
        with ExitStack() as stack:
            for broker in native_brokers:
                stack.enter_context(broker._run_lock)
            for strategy in self.strategies.values():
                if isinstance(strategy, Strategy) and (strategy._run_consumed or strategy.exchange is not self):
                    raise RuntimeError("Strategy already belongs to another run")
            if any(broker._run_consumed for broker in native_brokers):
                raise RuntimeError("Broker has already been used in another run")
            for strategy in self.strategies.values():
                if isinstance(strategy, Strategy):
                    strategy._run_consumed = True
            for broker in native_brokers:
                broker._run_consumed = True
                broker._run_owner = self
                broker._run_thread_id = get_ident()
            self._run_state = "running"

    @contextmanager
    def _read_only_brokers(self, brokers, phase):
        """控制与报告阶段只读账户，避免曲线结束点被回调额外交易改变。"""

        native_brokers = [broker for broker in brokers if isinstance(broker, Broker)]
        for broker in native_brokers:
            broker._run_readonly = phase
        try:
            yield
        finally:
            for broker in native_brokers:
                broker._run_readonly = None

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
        if isinstance(active_exception, GeneratorExit):
            active_exception = None  # 主动关闭生成器仍须暴露真正的资源关闭失败。
        close_errors = []
        for resource in reversed(resources):
            try:
                close = getattr(resource, "close", None)
                if callable(close):
                    close()
            except BaseException as exc:
                if active_exception is None:
                    close_errors.append(exc)
                else:
                    try:
                        self.logger.exception("failed to close %s", label)
                    except Exception:
                        pass  # 日志错误也不能覆盖已有业务异常。
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
            return MappingProxyType(payload)
        if callback == "on_trades":
            payload = OrderedDict()
            for item in items:
                event = item.event
                payload.setdefault(event.symbol, []).append(event.data)
            return MappingProxyType({symbol: tuple(rows) for symbol, rows in payload.items()})
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
        self._require_ready()
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
        with self._lifecycle_lock:
            self._require_ready()
            self._replace_source_ready(feed)

    def _replace_source_ready(self, feed) -> None:
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
