from collections import OrderedDict
from dataclasses import dataclass
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


class Exchange:
    """事件驱动的最简回测 Exchange。"""

    _FEED_ORDER = ("bars", "books", "trades", "news")

    def __init__(self, logger=None):
        self.strategies = OrderedDict()
        self.logger = logger or default_logger
        self._feeds: Dict[str, _Feed] = OrderedDict()
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

    def _to_rows(self, data) -> List[Dict]:
        if isinstance(data, list):
            if any(not isinstance(row, dict) for row in data):
                raise TypeError("list data must contain dictionaries")
            return [dict(row) for row in data]
        if isinstance(data, pl.DataFrame) or hasattr(data, "iter_rows"):
            return [dict(row) for row in data.iter_rows(named=True)]
        if isinstance(data, pd.DataFrame) or hasattr(data, "iterrows"):
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
            dt = row[date_key]
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

    def _all_datetimes(self) -> List:
        dts = set()
        for feed in self._feeds.values():
            dts.update(feed.grouped.keys())
        return sorted(dts)

    def _update_market_prices(self, feed: _Feed, dt, payload) -> None:
        if feed.price_key is None:
            return
        prices = OrderedDict()
        if feed.mode == "by_symbol":
            for symbol, row in payload.items():
                prices[symbol] = row[feed.price_key]
        elif feed.mode == "by_symbol_list":
            for symbol, rows in payload.items():
                prices[symbol] = rows[-1][feed.price_key]
        else:
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
        if not self._feeds:
            raise ValueError("Exchange data is not set; call set_bars() before run().")

        self.reset_market_state()
        self.logger.info(f"Start running {len(self.strategies)} strategies...")
        start_time = time.time()

        for strategy in self.strategies.values():
            strategy.on_init()

        step = 0
        for current_dt in self._all_datetimes():
            self._current_dt = current_dt
            slices = OrderedDict()
            for feed in self._feeds.values():
                if current_dt not in feed.grouped:
                    continue
                payload = feed.grouped[current_dt]
                slices[feed.name] = payload
                self._update_market_prices(feed, current_dt, payload)

            self._process_brokers_before_callbacks(current_dt, slices)

            for feed in self._feeds.values():
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
