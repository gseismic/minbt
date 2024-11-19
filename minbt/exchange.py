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
        # self._api = ExchangeAPI(history_size=history_size)
        self.reset_market_state()
    
    def _check_data(self, data, date_key):
        # 多symbol下，必须提供date-key，否则无法做时间对齐
        if date_key is None:
            num_symobls = len(set([s for s in data['symbol']]))
            if num_symobls != 1:
                raise ValueError(f'Data contains multiple symbols, but no date_key provided')
    
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
        elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            self.data = pl.DataFrame(data)
            self._is_polars_like = True
        else:
            raise TypeError(f"data type not supported: {type(data)}. Expected types are: pd.DataFrame, pl.DataFrame, or list of dictionaries.")
    
        # 如果提供了date_key，确保数据按时间和symbol稳定排序
        if date_key is not None:
            if self._is_polars_like:
                self.data = self.data.sort([date_key, "symbol"], descending=[False, False])
            elif isinstance(data, pd.DataFrame) or hasattr(data, 'iterrows'):
                self.data = self.data.sort_values([date_key, "symbol"], ascending=[True, True])
            else:
                raise TypeError(f"data type not supported: {type(data)}. Expected types are: pd.DataFrame, pl.DataFrame, or list of dictionaries.")

    def add_strategy(self, strategy: Strategy) -> None:
        assert hasattr(strategy, 'strategy_id'), 'strategy must have `strategy_id` attribute'
        assert hasattr(strategy, 'on_init'), 'strategy must have `on_init` method'
        assert hasattr(strategy, 'on_data'), 'strategy must have `on_data` method'
        assert hasattr(strategy, 'on_finish'), 'strategy must have `on_finish` method'
        strategy.set_exchange(self)
        self.strategies[strategy.strategy_id] = strategy
    
    def remove_strategy(self, strategy_id: str) -> None:
        self.strategies.pop(strategy_id)

    def reset_market_state(self):
        """重置市场价格相关的状态"""
        self._last_prices = {}
        self._last_price_dates = {}
        self._current_dt = None
        # self._api.reset()
        
    def run(self):
        self.reset_market_state()
        self.logger.info('[start_parallel]', len(self.strategies))
        start_time = time.time()
        for strategy in self.strategies.values():
            strategy.on_init()
        
        step = 0
        if self._is_polars_like:
            iter_method = enumerate(self.data.iter_rows(named=True))
        else:
            iter_method = self.data.iterrows()
        
        # idx = -1
        for idx, row in iter_method:
            # idx += 1
            for strategy in self.strategies.values():
                # 更新exchange价格数据
                print('idx', idx)
                print('row', row)
                symbol, price = row['symbol'], row['close']
                if self._date_key is not None:
                    current_dt = row[self._date_key]
                else:
                    current_dt = idx
                self._last_prices[symbol] = price
                self._last_price_dates[symbol] = current_dt
                self._current_dt = current_dt
                if strategy.broker:
                    strategy.broker.on_new_price(symbol, price, current_dt)
                strategy._on_exchange_data(row)
            step += 1

        for strategy in self.strategies.values():
            strategy.on_finish()
            
        total_time = time.time() - start_time
        self.logger.info('[all_complete]', total_time)
        self.logger.info(f'{total_time/step:.2f}s/step')
    
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

    @property
    def api(self):
        return self._api