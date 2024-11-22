from pyta_dev.utils.deque import DequeTable
from .logger import logger as default_logger
from typing import List

# currently deprecated: 请用户自己维护历史状态
# Note: 目前思考还不成熟，将来此模块[not-done]可能添加到主程序中
class ExchangeState:
    
    def __init__(self, history_size=1000, logger=None):
        self._history_size = history_size
        self.logger = logger or default_logger
        self._hist_data = DequeTable(maxlen=history_size)
        self._hist_dates = []
        self._last_prices = {}
        self._last_prices_dt = {}
        self._current_dt = None
    
    def _reset(self):
        self._hist_data.clear()
        self._last_prices.clear()
        self._last_prices_dt.clear()
        self._current_dt = None
    
    def _on_new_data(self, symbol, data, price, dt):
        self._hist_data.append(data)
        assert len(self._hist_dates) == 0 or self._hist_dates[-1] < dt
        self._hist_dates.append(dt)
        self._last_prices[data['symbol']] = price
        self._last_prices_dt[data['symbol']] = dt
        self._current_dt = dt
    
    def get_hist_data(self, symbol, start_dt, end_dt):
        pass
    
    def get_recent_data(self, symbol, n=1):
        assert n > 0, 'n must be greater than 0'
        assert n <= self.history_size, f'n must be less than or equal to {self.history_size}, got {n=}'
        pass
    
    def get_hist_prices(self, symbol, start_dt, end_dt):
        pass
    
    def get_recent_prices(self, symbol, n=1):
        assert n > 0, 'n must be greater than 0'
        assert n <= self.history_size, f'n must be less than or equal to {self.history_size}, got {n=}'
    
    def get_last_price(self, symbol, return_dt=False):
        pass
    
    def get_last_prices(self, symbols: List[str], return_dt=False):
        for symbol in symbols:
            pass
        pass
    
    def get_current_dt(self):
        return self._current_dt
