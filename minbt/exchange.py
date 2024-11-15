import pandas as pd
import polars as pl
from typing import List, Dict, Union
from multiprocessing import Pool
from .strategy import Strategy
from .logger import logger as default_logger
from tqdm import tqdm
import time

class Exchange:
    def __init__(self, logger=None):
        self.data = None
        self.strategies = []
        self.market_prices = {}
        self.logger = logger or default_logger
        self._is_polars = False
    
    def set_data(self, data: Union[pd.DataFrame, pl.DataFrame, List[Dict]]):
        """设置数据,支持Pandas DataFrame、Polars DataFrame或字典列表
        
        Args:
            data: 可以是pandas.DataFrame、polars.DataFrame或list[dict]格式
        """
        if isinstance(data, pl.DataFrame):
            self.data = data
            self._is_polars = True
        elif isinstance(data, pd.DataFrame):
            self.data = data
            self._is_polars = False
        elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            # 将字典列表转换为Polars DataFrame
            self.data = pl.DataFrame(data)
            self._is_polars = True
        else:
            raise TypeError(f"data type not supported: {type(data)}. Expected types are: pd.DataFrame, pl.DataFrame, or list of dictionaries.")
    
    def add_strategy(self, strategy: Strategy) -> None:
        assert hasattr(strategy, 'name'), 'strategy must have `name` attribute'
        assert hasattr(strategy, 'on_init'), 'strategy must have `on_init` method'
        assert hasattr(strategy, 'on_data'), 'strategy must have `on_data` method'
        assert hasattr(strategy, 'on_end'), 'strategy must have `on_end` method'
        strategy.set_exchange(self)
        self.strategies.append(strategy)
        
    def run(self):
        self.logger.info('[start_parallel]', len(self.strategies))
        start_time = time.time()
        for strategy in self.strategies:
            strategy.on_init()
        
        if self._is_polars:
            for row in self.data.iter_rows(named=True):
                for strategy in self.strategies:
                    self.market_prices[row['symbol']] = row['close']
                    strategy.on_data(row)
        else:
            for _, row in self.data.iterrows():
                for strategy in self.strategies:
                    self.market_prices[row['symbol']] = row['close']
                    strategy.on_data(row)

        for strategy in self.strategies:
            strategy.on_end()
            
        total_time = time.time() - start_time
        self.logger.info('[all_complete]', total_time)
    
    def get_market_price(self, symbol: str) -> float:
        return self.market_prices.get(symbol, None)
    
    def get_market_prices(self) -> Dict[str, float]:
        return self.market_prices.copy()
            
            