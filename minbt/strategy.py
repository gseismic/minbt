from typing import Dict, Optional, Protocol, runtime_checkable
from .broker import Broker
from .logger import logger as default_logger

@runtime_checkable
class BrokerProtocol(Protocol):
    def submit_market_order(
        self,
        symbol: str,
        qty: float,
        price: Optional[float] = None,
        leverage: Optional[float] = None,
        price_dt=None,
        portfolio_id: str = 'default'
    ): ...
    def get_position_size(self, symbol: str, portfolio_id: Optional[str] = None) -> float: ...
    def get_position_sizes(self, portfolio_id: Optional[str] = None) -> Dict[str, float]: ...
    def get_total_equity(self) -> float: ...
    def get_equity(self, portfolio_id: Optional[str] = None) -> float: ...
    def get_cash(self, include_locked: bool = False, portfolio_id: Optional[str] = None) -> float: ...
    def get_positions(self, portfolio_id: Optional[str] = None): ...

class Strategy:
    def __init__(self,
                 strategy_id: str,
                 broker: Optional[Broker]=None,
                 params: dict=None,
                 logger=None):
        """
        Args:
            strategy_id: 策略ID
            broker: 交易代理
            params: 参数
            logger: 日志记录器
        """
        self.strategy_id = strategy_id
        self.set_broker(broker)
        self.params = params if params is not None else {}
        self.logger = logger or default_logger
        self._equity_history = None
        self._position_size_history = None
        self._pyta_available = None

    def _check_pyta(self):
        if self._pyta_available is None:
            try:
                from pyta_dev.utils.vector import NumpyVector, VectorTable
                self._pyta_NumpyVector = NumpyVector
                self._pyta_VectorTable = VectorTable
                self._pyta_available = True
            except ImportError:
                self._pyta_available = False

    def set_broker(self, broker):
        if broker is None:
            self.broker = None
            return
        assert isinstance(broker, BrokerProtocol), (
            f'broker must implement BrokerProtocol (submit_market_order, get_position_size, get_total_equity), '
            f'got {type(broker).__name__}'
        )
        self.broker = broker

    def set_params(self, params: dict):
        self.params = params

    def update_params(self, **kwargs):
        self.params.update(kwargs)

    def set_exchange(self, exchange):
        self.exchange = exchange

    def on_init(self):
        pass

    def _on_exchange_data(self, data):
        self.on_data(data)
        if self.broker is None:
            return

        if self._equity_history is None:
            self._check_pyta()
            if self._pyta_available:
                self._equity_history = self._pyta_NumpyVector()
            else:
                self._equity_history = []

        if self._position_size_history is None:
            self._check_pyta()
            if self._pyta_available:
                self._position_size_history = self._pyta_VectorTable()
            else:
                self._position_size_history = []

        equity = self.broker.get_total_equity()
        self._equity_history.append(equity)

        positions = self.broker.get_position_sizes()
        self._position_size_history.append(positions)

    def on_data(self, data):
        pass

    def on_finish(self):
        pass
    
    def get_hist_equity(self):
        if self._equity_history is None:
            return []
        if isinstance(self._equity_history, list):
            return self._equity_history
        return self._equity_history.to_numpy()
    
    def get_hist_position_sizes(self, symbol: str):
        if self._position_size_history is None:
            return []
        if isinstance(self._position_size_history, list):
            return [p.get(symbol, 0) for p in self._position_size_history]
        return self._position_size_history.get_column(symbol)
    
    def get_broker_stats(self, portfolio_id: str = 'default'):
        return {
            'equity': self.broker.get_equity(portfolio_id=portfolio_id),
            'cash': self.broker.get_cash(portfolio_id=portfolio_id),
            'positions': self.broker.get_positions(portfolio_id=portfolio_id)
        }
    
    def market_buy(self, symbol: str, qty: float, portfolio_id: str = 'default'):
        assert qty > 0, f'qty must be positive, got {qty}'
        return self.broker.submit_market_order(symbol, qty=qty, portfolio_id=portfolio_id)
    
    def market_sell(self, symbol: str, qty: float, portfolio_id: str = 'default'):
        assert qty > 0, f'qty must be positive, got {qty}'
        return self.broker.submit_market_order(symbol, qty=-qty, portfolio_id=portfolio_id)
    
    def market_order(self, symbol: str, qty: float, portfolio_id: str = 'default'):
        assert qty != 0, f'qty must be non-zero, got {qty}'
        return self.broker.submit_market_order(symbol, qty=qty, portfolio_id=portfolio_id)
