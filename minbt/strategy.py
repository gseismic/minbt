from typing import Dict, Optional, Protocol, runtime_checkable

from .broker import Broker, Order
from .logger import logger as default_logger


BROKER_PROTOCOL_METHODS = (
    "submit_market_order",
    "submit_limit_order",
    "cancel_order",
    "get_position_size",
    "get_position_sizes",
    "get_total_equity",
    "get_equity",
    "get_cash",
    "get_positions",
    "order_target_size",
    "order_target_value",
    "order_target_percent",
    "close_position",
    "close_portfolio",
    "set_exit",
    "clear_exit",
    "get_exit",
    "add_exit",
)


@runtime_checkable
class BrokerProtocol(Protocol):
    def submit_market_order(self, symbol: str, qty: float, price: Optional[float] = None, **kwargs) -> Order: ...
    def submit_limit_order(self, symbol: str, qty: float, limit_price: float, **kwargs) -> Order: ...
    def cancel_order(self, order_id: str) -> Order: ...
    def get_position_size(self, symbol: str, *, portfolio: str = "main") -> float: ...
    def get_position_sizes(self, *, portfolio: str = "main") -> Dict[str, float]: ...
    def get_total_equity(self) -> float: ...
    def get_equity(self, portfolio: str = "main") -> float: ...
    def get_cash(self, include_locked: bool = False, *, portfolio: str = "main") -> float: ...
    def get_positions(self, *, portfolio: str = "main"): ...
    def order_target_size(self, symbol: str, target_size: float, price: Optional[float] = None, **kwargs) -> Order: ...
    def order_target_value(self, symbol: str, target_value: float, price: Optional[float] = None, **kwargs) -> Order: ...
    def order_target_percent(self, symbol: str, target_percent: float, price: Optional[float] = None, **kwargs) -> Order: ...
    def close_position(self, symbol: str, price: Optional[float] = None, **kwargs) -> Order: ...
    def close_portfolio(self, portfolio: str = "main"): ...
    def set_exit(self, order_id: str, **kwargs): ...
    def clear_exit(self, order_id: str, **kwargs): ...
    def get_exit(self, order_id: str): ...
    def add_exit(self, order_id: str, condition, **kwargs): ...


class Strategy:
    def __init__(
        self,
        strategy_id: str,
        broker: Optional[Broker] = None,
        params: Optional[dict] = None,
        logger=None,
    ):
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
        if not isinstance(broker, BrokerProtocol):
            raise TypeError(
                f"broker must implement BrokerProtocol ({', '.join(BROKER_PROTOCOL_METHODS)}), "
                f"got {type(broker).__name__}"
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

    def on_bars(self, dt, bars):
        pass

    def on_books(self, dt, books):
        pass

    def on_trades(self, dt, trades):
        pass

    def on_news(self, dt, news):
        pass

    def on_finish(self):
        pass

    def _ensure_broker_history(self):
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

    def _record_broker_history(self):
        if self.broker is None:
            return

        self._ensure_broker_history()
        equity = self.broker.get_total_equity()
        self._equity_history.append(equity)

        positions = self.broker.get_position_sizes()
        self._position_size_history.append(positions)

    def _dispatch_exchange_callback(self, name: str, dt, data):
        getattr(self, name)(dt, data)

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

    def get_broker_stats(self, portfolio: str = "main"):
        return {
            "equity": self.broker.get_equity(portfolio=portfolio),
            "cash": self.broker.get_cash(portfolio=portfolio),
            "positions": self.broker.get_positions(portfolio=portfolio),
        }

    def market_buy(self, symbol: str, qty: float, portfolio: str = "main") -> Order:
        if qty <= 0:
            raise ValueError(f"qty must be positive, got {qty}")
        return self.broker.submit_market_order(symbol, qty=qty, portfolio=portfolio)

    def market_sell(self, symbol: str, qty: float, portfolio: str = "main") -> Order:
        if qty <= 0:
            raise ValueError(f"qty must be positive, got {qty}")
        return self.broker.submit_market_order(symbol, qty=-qty, portfolio=portfolio)

    def market_order(self, symbol: str, qty: float, portfolio: str = "main") -> Order:
        if qty == 0:
            raise ValueError(f"qty must be non-zero, got {qty}")
        return self.broker.submit_market_order(symbol, qty=qty, portfolio=portfolio)
