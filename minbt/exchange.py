from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from numbers import Number
import time
from typing import Dict, List, Optional, Union

import pandas as pd
import polars as pl

from .logger import logger as default_logger
from .strategy import Strategy


@dataclass
class _Feed:
    name: str
    callback: str
    mode: str
    price_key: Optional[str]
    grouped: OrderedDict
    prices: Optional[Dict] = None


class Exchange:
    """事件驱动的最简回测 Exchange。"""

    _FEED_ORDER = ("bars", "books", "trades", "news")

    def __init__(self, logger=None):
        self.strategies = OrderedDict()
        self.logger = logger or default_logger
        self._feeds: Dict[str, _Feed] = OrderedDict()
        self._data_feeds = OrderedDict()
        self.reset_market_state()

    def set_bars(
        self,
        data: Union[pd.DataFrame, pl.DataFrame, List[Dict]],
        *,
        date_key: str = "dt",
        symbol_key: str = "symbol",
        price_key: str = "close",
    ) -> None:
        self._set_feed(
            "bars",
            "on_bars",
            data,
            date_key=date_key,
            symbol_key=symbol_key,
            price_key=price_key,
            mode="by_symbol",
            require_unique=True,
        )

    def set_books(
        self,
        data: Union[pd.DataFrame, pl.DataFrame, List[Dict]],
        *,
        date_key: str = "dt",
        symbol_key: str = "symbol",
        price_key: Optional[str] = None,
    ) -> None:
        self._set_feed(
            "books",
            "on_books",
            data,
            date_key=date_key,
            symbol_key=symbol_key,
            price_key=price_key,
            mode="by_symbol",
            require_unique=True,
        )

    def set_trades(
        self,
        data: Union[pd.DataFrame, pl.DataFrame, List[Dict]],
        *,
        date_key: str = "dt",
        symbol_key: str = "symbol",
        price_key: str = "price",
    ) -> None:
        self._set_feed(
            "trades",
            "on_trades",
            data,
            date_key=date_key,
            symbol_key=symbol_key,
            price_key=price_key,
            mode="by_symbol_list",
            require_unique=False,
        )

    def set_news(
        self,
        data: Union[pd.DataFrame, pl.DataFrame, List[Dict]],
        *,
        date_key: str = "dt",
    ) -> None:
        self._set_feed(
            "news",
            "on_news",
            data,
            date_key=date_key,
            symbol_key=None,
            price_key=None,
            mode="list",
            require_unique=False,
        )

    def add_feed(self, feed) -> None:
        name = getattr(feed, "name", None)
        event_type = getattr(feed, "event_type", None)
        if not isinstance(name, str) or not name:
            raise TypeError("feed must have a non-empty string `name` attribute")
        if not isinstance(event_type, str) or not event_type:
            raise TypeError("feed must have a non-empty string `event_type` attribute")
        if event_type not in self._FEED_ORDER:
            raise ValueError(f"feed event_type must be one of {self._FEED_ORDER}, got {event_type!r}")
        if not callable(getattr(feed, "events", None)):
            raise TypeError("feed must have an `events()` method")
        if getattr(feed, "is_live", False):
            raise NotImplementedError("live feed is not supported in the current replay-only Exchange")
        if name in self._data_feeds:
            raise ValueError(f"feed name already exists: {name!r}")
        self._data_feeds[name] = feed

    def add_strategy(self, strategy: Strategy) -> None:
        if not hasattr(strategy, "strategy_id"):
            raise TypeError("strategy must have `strategy_id` attribute")
        for method in ("on_init", "on_bars", "on_books", "on_trades", "on_news", "on_finish"):
            if not hasattr(strategy, method):
                raise TypeError(f"strategy must have `{method}` method")
        strategy.set_exchange(self)
        self.strategies[strategy.strategy_id] = strategy

    def remove_strategy(self, strategy_id: str) -> None:
        self.strategies.pop(strategy_id)

    def reset_market_state(self) -> None:
        self._last_prices = {}
        self._last_price_dates = {}
        self._current_dt = None

    def _set_feed(
        self,
        name: str,
        callback: str,
        data,
        *,
        date_key: str,
        symbol_key: Optional[str],
        price_key: Optional[str],
        mode: str,
        require_unique: bool,
    ) -> None:
        rows = self._to_rows(data)
        required_columns = [date_key]
        if symbol_key is not None:
            required_columns.append(symbol_key)
        if price_key is not None:
            required_columns.append(price_key)
        self._validate_required_columns(rows, required_columns, name, data=data)
        grouped = self._group_rows(
            rows,
            date_key=date_key,
            symbol_key=symbol_key,
            mode=mode,
            require_unique=require_unique,
            feed_name=name,
        )
        self._feeds[name] = _Feed(
            name=name,
            callback=callback,
            mode=mode,
            price_key=price_key,
            grouped=grouped,
        )
        self._sort_feeds()

    def _sort_feeds(self) -> None:
        ordered = OrderedDict()
        for name in self._FEED_ORDER:
            if name in self._feeds:
                ordered[name] = self._feeds[name]
        self._feeds = ordered

    def _copy_feeds(self) -> OrderedDict:
        copied = OrderedDict()
        for name, feed in self._feeds.items():
            grouped = OrderedDict()
            for dt, payload in feed.grouped.items():
                grouped[dt] = self._copy_payload(feed.mode, payload)
            prices = None
            if feed.prices is not None:
                prices = OrderedDict((dt, OrderedDict(values)) for dt, values in feed.prices.items())
            copied[name] = _Feed(
                name=feed.name,
                callback=feed.callback,
                mode=feed.mode,
                price_key=feed.price_key,
                grouped=grouped,
                prices=prices,
            )
        return copied

    def _copy_payload(self, mode: str, payload):
        if mode == "by_symbol":
            return OrderedDict((symbol, dict(row)) for symbol, row in payload.items())
        if mode == "by_symbol_list":
            return OrderedDict((symbol, [dict(row) for row in rows]) for symbol, rows in payload.items())
        if mode == "list":
            return [dict(row) for row in payload]
        return payload

    def _run_feeds(self) -> OrderedDict:
        feeds = self._copy_feeds()
        for feed in self._data_feeds.values():
            self._materialize_data_feed(feeds, feed)
        return self._sort_feed_mapping(feeds)

    def _sort_feed_mapping(self, feeds: OrderedDict) -> OrderedDict:
        ordered = OrderedDict()
        for name in self._FEED_ORDER:
            if name in feeds:
                ordered[name] = feeds[name]
        return ordered

    def _materialize_data_feed(self, feeds: OrderedDict, data_feed) -> None:
        prepare = getattr(data_feed, "prepare", None)
        close = getattr(data_feed, "close", None)
        if callable(prepare):
            prepare()
        try:
            for event in data_feed.events():
                self._add_feed_event(feeds, data_feed, event)
        finally:
            if callable(close):
                close()

    def _add_feed_event(self, feeds: OrderedDict, data_feed, event) -> None:
        event_type = getattr(event, "event_type", None)
        if event_type != data_feed.event_type:
            raise ValueError(
                f"feed {data_feed.name!r} produced event_type {event_type!r}, "
                f"expected {data_feed.event_type!r}"
            )
        if event_type not in self._FEED_ORDER:
            raise ValueError(f"unsupported feed event_type: {event_type!r}")
        if not isinstance(event.dt, datetime):
            raise ValueError("FeedEvent.dt must be datetime.datetime")
        dt = self._normalize_dt(event.dt)

        mode = self._feed_mode(event_type)
        target = feeds.get(event_type)
        if target is None:
            target = _Feed(
                name=event_type,
                callback=f"on_{event_type}",
                mode=mode,
                price_key=self._feed_price_key(event_type),
                grouped=OrderedDict(),
                prices=OrderedDict(),
            )
            feeds[event_type] = target
        if target.mode != mode:
            raise ValueError(f"feed mode mismatch for event_type {event_type!r}")

        self._merge_payload(target, dt, event.data, feed_name=data_feed.name)
        self._merge_event_prices(target, dt, event.prices, feed_name=data_feed.name)

    def _feed_mode(self, event_type: str) -> str:
        if event_type in ("bars", "books"):
            return "by_symbol"
        if event_type == "trades":
            return "by_symbol_list"
        if event_type == "news":
            return "list"
        raise ValueError(f"unsupported feed event_type: {event_type!r}")

    def _feed_price_key(self, event_type: str) -> Optional[str]:
        if event_type == "bars":
            return "close"
        if event_type == "trades":
            return "price"
        return None

    def _merge_payload(self, target: _Feed, dt, payload, *, feed_name: str) -> None:
        if target.mode == "by_symbol":
            if not isinstance(payload, dict):
                raise TypeError(f"{feed_name} {target.name} event data must be dict by symbol")
            current = target.grouped.setdefault(dt, OrderedDict())
            for symbol, row in payload.items():
                if symbol in current:
                    raise ValueError(f"{target.name} data contains duplicate ({dt!r}, {symbol!r}) rows")
                if not isinstance(row, dict):
                    raise TypeError(f"{feed_name} {target.name} row must be a dictionary")
                copied = dict(row)
                self._validate_standard_row(target.name, copied, symbol=symbol)
                copied["dt"] = self._normalize_dt(copied.get("dt", dt))
                copied.setdefault("symbol", symbol)
                current[symbol] = copied
            return

        if target.mode == "by_symbol_list":
            if not isinstance(payload, dict):
                raise TypeError(f"{feed_name} {target.name} event data must be dict by symbol")
            current = target.grouped.setdefault(dt, OrderedDict())
            for symbol, rows in payload.items():
                if not isinstance(rows, list):
                    raise TypeError(f"{feed_name} {target.name} symbol payload must be a list")
                copied_rows = []
                for row in rows:
                    copied = dict(row)
                    self._validate_standard_row(target.name, copied, symbol=symbol)
                    copied["dt"] = self._normalize_dt(copied.get("dt", dt))
                    copied.setdefault("symbol", symbol)
                    copied_rows.append(copied)
                current.setdefault(symbol, []).extend(copied_rows)
            return

        if target.mode == "list":
            if not isinstance(payload, list):
                raise TypeError(f"{feed_name} {target.name} event data must be a list")
            copied_rows = []
            for row in payload:
                copied = dict(row)
                self._validate_standard_row(target.name, copied)
                copied["dt"] = self._normalize_dt(copied.get("dt", dt))
                copied_rows.append(copied)
            target.grouped.setdefault(dt, []).extend(copied_rows)
            return

        raise ValueError(f"unknown feed mode: {target.mode}")

    def _validate_standard_row(self, feed_name: str, row: dict, *, symbol=None) -> None:
        required = {
            "bars": ("close",),
            "books": (),
            "trades": ("price",),
            "news": (),
        }.get(feed_name, ())
        missing = [field for field in required if field not in row]
        if symbol is not None and row.get("symbol", symbol) != symbol:
            raise ValueError(f"{feed_name} row symbol does not match payload key: {symbol!r}")
        if missing:
            raise ValueError(f"{feed_name} event row missing required fields: {missing}")

    def _merge_event_prices(self, target: _Feed, dt, prices, *, feed_name: str) -> None:
        derived_prices = self._payload_prices(target, dt)
        if prices is None:
            prices = derived_prices
        else:
            prices = OrderedDict((symbol, float(price)) for symbol, price in prices.items())
            for symbol, price in derived_prices.items():
                if symbol in prices and prices[symbol] != price:
                    raise ValueError(
                        f"{feed_name} price conflict for {symbol!r} at {dt!r}: "
                        f"{prices[symbol]!r} != {price!r}"
                    )
                prices.setdefault(symbol, price)

        if not prices:
            return
        if target.prices is None:
            target.prices = OrderedDict()
        current = target.prices.setdefault(dt, OrderedDict())
        for symbol, price in prices.items():
            if symbol in current and current[symbol] != price:
                raise ValueError(
                    f"{target.name} price conflict for {symbol!r} at {dt!r}: "
                    f"{current[symbol]!r} != {price!r}"
                )
            current[symbol] = price

    def _payload_prices(self, feed: _Feed, dt) -> OrderedDict:
        prices = OrderedDict()
        if feed.price_key is None or dt not in feed.grouped:
            return prices
        payload = feed.grouped[dt]
        if feed.mode == "by_symbol":
            for symbol, row in payload.items():
                if feed.price_key in row:
                    prices[symbol] = float(row[feed.price_key])
        elif feed.mode == "by_symbol_list":
            for symbol, rows in payload.items():
                if rows and feed.price_key in rows[-1]:
                    prices[symbol] = float(rows[-1][feed.price_key])
        return prices

    def _to_rows(self, data) -> List[Dict]:
        if isinstance(data, list):
            if any(not isinstance(row, dict) for row in data):
                raise TypeError("list data must contain dictionaries")
            return [dict(row) for row in data]
        if isinstance(data, pl.DataFrame) or hasattr(data, "iter_rows"):
            return [dict(row) for row in data.iter_rows(named=True)]
        if isinstance(data, pd.DataFrame):
            return [dict(row) for row in data.to_dict("records")]
        if hasattr(data, "to_dict") and hasattr(data, "columns"):
            try:
                rows = data.to_dict("records")
            except TypeError:
                rows = None
            if rows is not None:
                if any(not isinstance(row, dict) for row in rows):
                    raise TypeError("data.to_dict('records') must return dictionaries")
                return [dict(row) for row in rows]
        if hasattr(data, "iterrows"):
            return [row.to_dict() for _, row in data.iterrows()]
        raise TypeError(
            f"data type not supported: {type(data)}. "
            "Expected pd.DataFrame, pl.DataFrame, or list[dict]."
        )

    def _data_columns(self, data, rows: List[Dict]) -> set:
        if hasattr(data, "columns"):
            return set(data.columns)
        columns = set()
        for row in rows:
            columns.update(row.keys())
        return columns

    def _validate_required_columns(self, rows: List[Dict], required_columns: List[str], feed_name: str, *, data) -> None:
        columns = self._data_columns(data, rows)
        missing_columns = sorted(set(required_columns) - columns)
        if missing_columns:
            raise ValueError(f"{feed_name} data missing required columns: {missing_columns}")

    def _group_rows(
        self,
        rows: List[Dict],
        *,
        date_key: str,
        symbol_key: Optional[str],
        mode: str,
        require_unique: bool,
        feed_name: str,
    ) -> OrderedDict:
        sorted_rows = sorted(
            rows,
            key=lambda row: (row[date_key], row[symbol_key] if symbol_key is not None else 0),
        )
        grouped = OrderedDict()
        seen = set()
        duplicate_keys = []

        for row in sorted_rows:
            dt = self._normalize_dt(row[date_key])
            row = dict(row)
            row[date_key] = dt
            if mode == "by_symbol":
                symbol = row[symbol_key]
                key = (dt, symbol)
                if require_unique and key in seen:
                    duplicate_keys.append(key)
                seen.add(key)
                grouped.setdefault(dt, OrderedDict())[symbol] = row
            elif mode == "by_symbol_list":
                symbol = row[symbol_key]
                grouped.setdefault(dt, OrderedDict()).setdefault(symbol, []).append(row)
            elif mode == "list":
                grouped.setdefault(dt, []).append(row)
            else:
                raise ValueError(f"unknown feed mode: {mode}")

        if duplicate_keys:
            preview = ", ".join(f"({dt!r}, {symbol!r})" for dt, symbol in duplicate_keys[:5])
            if len(duplicate_keys) > 5:
                preview += ", ..."
            raise ValueError(f"{feed_name} data contains duplicate ({date_key}, {symbol_key}) rows: {preview}")
        return grouped

    def _normalize_dt(self, value):
        try:
            if isinstance(value, Number) and not isinstance(value, bool):
                timestamp = pd.to_datetime(value, unit=self._infer_epoch_unit(value), utc=True)
            else:
                timestamp = pd.Timestamp(value)
        except Exception as exc:
            raise ValueError(f"dt cannot be converted to datetime: {value!r}") from exc
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        return timestamp.to_pydatetime()

    def _infer_epoch_unit(self, value) -> str:
        abs_value = abs(float(value))
        if abs_value >= 1e17:
            return "ns"
        if abs_value >= 1e14:
            return "us"
        if abs_value >= 1e11:
            return "ms"
        return "s"

    def _all_datetimes(self, feeds: Optional[OrderedDict] = None) -> List:
        feeds = feeds if feeds is not None else self._feeds
        dts = set()
        for feed in feeds.values():
            dts.update(feed.grouped.keys())
        return sorted(dts, key=self._dt_sort_key)

    def _dt_sort_key(self, dt):
        try:
            timestamp = pd.Timestamp(self._normalize_dt(dt))
            return (0, timestamp.value)
        except Exception:
            return (1, str(dt))

    def _update_market_prices(self, feed: _Feed, dt, payload) -> None:
        if feed.price_key is None:
            prices = OrderedDict()
        else:
            prices = self._payload_prices(feed, dt)
        if feed.prices is not None and dt in feed.prices:
            for symbol, price in feed.prices[dt].items():
                if symbol in prices and prices[symbol] != price:
                    raise ValueError(
                        f"{feed.name} price conflict for {symbol!r} at {dt!r}: "
                        f"{prices[symbol]!r} != {price!r}"
                    )
                prices[symbol] = price
        if not prices:
            return

        self._current_dt = dt
        for symbol, price in prices.items():
            self._last_prices[symbol] = price
            self._last_price_dates[symbol] = dt

        for broker in self._unique_brokers():
            for symbol, price in prices.items():
                broker.on_new_price(symbol, price, dt)

    def _unique_brokers(self):
        seen = set()
        for strategy in self.strategies.values():
            broker = getattr(strategy, "broker", None)
            if broker is None:
                continue
            broker_id = id(broker)
            if broker_id in seen:
                continue
            seen.add(broker_id)
            yield broker

    def _process_brokers_before_callbacks(self, dt, slices) -> None:
        for broker in self._unique_brokers():
            broker.process_pending_orders(dt=dt)
            broker.check_exit_rules(dt=dt, data=slices)

    def run(self) -> None:
        if not self._feeds and not self._data_feeds:
            raise ValueError("Exchange data is not set; call set_bars() or add_feed() before run().")

        self.reset_market_state()
        feeds = self._run_feeds()
        self.logger.info(f"Start running {len(self.strategies)} strategies...")
        start_time = time.time()

        for strategy in self.strategies.values():
            strategy.on_init()

        step = 0
        for current_dt in self._all_datetimes(feeds):
            self._current_dt = current_dt
            slices = OrderedDict()
            for feed in feeds.values():
                if current_dt not in feed.grouped:
                    continue
                payload = feed.grouped[current_dt]
                slices[feed.name] = payload
                self._update_market_prices(feed, current_dt, payload)

            self._process_brokers_before_callbacks(current_dt, slices)

            for feed in feeds.values():
                if feed.name not in slices:
                    continue
                payload = slices[feed.name]
                for strategy in self.strategies.values():
                    strategy._dispatch_exchange_callback(feed.callback, current_dt, payload)

            for strategy in self.strategies.values():
                strategy._record_broker_history()
            step += 1

        for strategy in self.strategies.values():
            strategy.on_finish()

        total_time = time.time() - start_time
        self.logger.info(f"All strategies completed, total time: {total_time:.2f}s")
        if step > 0:
            self.logger.info(f"{total_time / step:.2f}s/step")
        else:
            self.logger.info("0 steps")

    def get_last_price(self, symbol: str, return_dt: bool = False):
        price = self._last_prices.get(symbol)
        if return_dt:
            return price, self._last_price_dates.get(symbol)
        return price

    def get_last_prices(self) -> Dict[str, float]:
        return self._last_prices.copy()

    def get_current_dt(self):
        return self._current_dt
