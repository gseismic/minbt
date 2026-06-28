import pandas as pd
import polars as pl
from typing import List, Dict, Union, Optional
from collections import OrderedDict
from .strategy import Strategy
from .logger import logger as default_logger
import time


class Exchange:
    """
    轻量级： 不维护API，用户需要历史数据，自己存取
    """
    
    def __init__(self, logger=None):
        self.data = None
        self.strategies = OrderedDict()
        self.logger = logger or default_logger
        self._is_polars_like = False
        self._date_key = None
        self.reset_market_state()
    
    def _check_data(self, data, date_key):
        self._validate_data_columns(data, date_key)
        if date_key is not None:
            return
        # date_key is None: must have exactly one symbol
        if isinstance(data, list):
            symbols = set(d.get('symbol') for d in data if isinstance(d, dict))
        elif isinstance(data, (pd.DataFrame, pl.DataFrame)) or hasattr(data, '__getitem__'):
            symbols = set(data['symbol'])
        else:
            raise TypeError(f"Cannot inspect symbols from data type: {type(data)}")
        if len(symbols) != 1:
            raise ValueError(f'Data contains {len(symbols)} symbols, but no date_key provided')
    
    def set_data(self, data: Union[pd.DataFrame, pl.DataFrame, List[Dict]], date_key: Optional[str] = None):
        """设置数据,支持Pandas DataFrame、Polars DataFrame或字典列表
        
        date_key 为None时，使用行号作为时间戳，这时要求只能是单symbol
        数据会按照date_key和symbol稳定排序（如果提供date_key）
        
        Args:
            data: 可以是pandas.DataFrame、polars.DataFrame或list[dict]格式
            date_key: 日期列的键名
        """
        self._check_data(data, date_key)
        self._date_key = date_key
        if isinstance(data, pl.DataFrame) or hasattr(data, 'iter_rows'):
            self.data = data
            self._is_polars_like = True
        elif isinstance(data, pd.DataFrame) or hasattr(data, 'iterrows'):
            self.data = data
            self._is_polars_like = False
        elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
            self.data = list(data)
            self._is_polars_like = False
        else:
            raise TypeError(f"data type not supported: {type(data)}. Expected types are: pd.DataFrame, pl.DataFrame, or list of dictionaries.")
    
        self._validate_unique_bar_symbols()
        if date_key is not None:
            if isinstance(self.data, list):
                self.data = sorted(self.data, key=lambda row: (row[date_key], row["symbol"]))
            elif self._is_polars_like:
                self.data = self.data.sort([date_key, "symbol"], descending=[False, False])
            else:
                self.data = self.data.sort_values([date_key, "symbol"], ascending=[True, True])

    def add_strategy(self, strategy: Strategy) -> None:
        if not hasattr(strategy, 'strategy_id'):
            raise TypeError('strategy must have `strategy_id` attribute')
        if not hasattr(strategy, 'on_init'):
            raise TypeError('strategy must have `on_init` method')
        if not hasattr(strategy, 'on_data'):
            raise TypeError('strategy must have `on_data` method')
        if not hasattr(strategy, 'on_bar'):
            raise TypeError('strategy must have `on_bar` method')
        if not hasattr(strategy, 'on_finish'):
            raise TypeError('strategy must have `on_finish` method')
        strategy.set_exchange(self)
        self.strategies[strategy.strategy_id] = strategy
    
    def remove_strategy(self, strategy_id: str) -> None:
        self.strategies.pop(strategy_id)

    def reset_market_state(self):
        """重置市场价格相关的状态"""
        self._last_prices = {}
        self._last_price_dates = {}
        self._current_dt = None

    def _get_data_columns(self, data) -> set:
        if isinstance(data, list):
            columns = set()
            for item in data:
                if isinstance(item, dict):
                    columns.update(item.keys())
            return columns
        if hasattr(data, 'columns'):
            return set(data.columns)
        return set()

    def _validate_data_columns(self, data, date_key) -> None:
        required_columns = {'symbol', 'close'}
        if date_key is not None:
            required_columns.add(date_key)
        columns = self._get_data_columns(data)
        missing_columns = sorted(required_columns - columns)
        if missing_columns:
            raise ValueError(f"data missing required columns: {missing_columns}")

    def _iter_data_rows(self):
        if isinstance(self.data, list):
            yield from enumerate(self.data)
            return
        if self._is_polars_like:
            yield from enumerate(self.data.iter_rows(named=True))
        else:
            for row_number, (_, row) in enumerate(self.data.iterrows()):
                yield row_number, row

    def _get_row_dt(self, idx, row):
        if self._date_key is not None:
            return row[self._date_key]
        return idx

    def _get_row_symbol_price(self, row):
        return row['symbol'], row['close']

    def _validate_unique_bar_symbols(self) -> None:
        if self._date_key is None:
            return

        seen = set()
        duplicate_keys = []
        duplicate_seen = set()
        for _, row in self._iter_data_rows():
            key = (row[self._date_key], row['symbol'])
            if key in seen and key not in duplicate_seen:
                duplicate_keys.append(key)
                duplicate_seen.add(key)
            seen.add(key)

        if duplicate_keys:
            preview = ', '.join(
                f"({dt!r}, {symbol!r})" for dt, symbol in duplicate_keys[:5]
            )
            if len(duplicate_keys) > 5:
                preview += ', ...'
            raise ValueError(
                f"data contains duplicate ({self._date_key}, symbol) rows: {preview}"
            )

    def _iter_bars(self):
        current_dt = None
        current_rows = []
        has_current_dt = False

        for idx, row in self._iter_data_rows():
            row_dt = self._get_row_dt(idx, row)
            if has_current_dt and row_dt != current_dt:
                yield current_dt, current_rows
                current_rows = []
            current_dt = row_dt
            has_current_dt = True
            current_rows.append(row)

        if has_current_dt:
            yield current_dt, current_rows

    def _update_market_state_for_bar(self, dt, rows):
        self._current_dt = dt
        for row in rows:
            symbol, price = self._get_row_symbol_price(row)
            self._last_prices[symbol] = price
            self._last_price_dates[symbol] = dt

    def _update_strategy_brokers_for_bar(self, dt, rows):
        updated_broker_ids = set()
        for strategy in self.strategies.values():
            broker = strategy.broker
            if not broker:
                continue
            broker_id = id(broker)
            if broker_id in updated_broker_ids:
                continue
            for row in rows:
                symbol, price = self._get_row_symbol_price(row)
                broker.on_new_price(symbol, price, dt)
            updated_broker_ids.add(broker_id)

    def _rows_by_symbol(self, rows):
        rows_by_symbol = OrderedDict()
        for row in rows:
            symbol, _ = self._get_row_symbol_price(row)
            rows_by_symbol[symbol] = row
        return rows_by_symbol
        
    def run(self):
        if self.data is None:
            raise ValueError("Exchange data is not set; call set_data() before run().")

        self.reset_market_state()
        self.logger.info('[start_parallel]', len(self.strategies))
        start_time = time.time()
        for strategy in self.strategies.values():
            strategy.on_init()
        
        step = 0

        for current_dt, rows in self._iter_bars():
            self._update_market_state_for_bar(current_dt, rows)

            self._update_strategy_brokers_for_bar(current_dt, rows)

            for row in rows:
                for strategy in self.strategies.values():
                    strategy._on_exchange_data(row, record_history=False)

            rows_by_symbol = self._rows_by_symbol(rows)
            for strategy in self.strategies.values():
                strategy._on_exchange_bar(current_dt, rows_by_symbol)
            step += 1

        for strategy in self.strategies.values():
            strategy.on_finish()
            
        total_time = time.time() - start_time
        self.logger.info('[all_complete]', total_time)
        if step > 0:
            self.logger.info(f'{total_time/step:.2f}s/step')
        else:
            self.logger.info('0 steps')
    
    def get_last_price(self, symbol: str, return_dt: bool = False):
        price = self._last_prices.get(symbol, None)
        if return_dt:
            return price, self._last_price_dates.get(symbol, None)
        else:
            return price

    def get_last_prices(self) -> Dict[str, float]:
        return self._last_prices.copy()

    def get_current_dt(self):
        return self._current_dt
