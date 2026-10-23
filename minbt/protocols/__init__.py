"""集中定义扩展契约，不加载具体读取或交易实现。"""

from .broker import BrokerProtocol, ReplayBrokerProtocol
from .data import DataFeedProtocol
from .engine import BrokerFactory, Config, EngineProtocol, FeedFactory
from .result import OrderProtocol, OrderSnapshot, PnlProtocol, ResultProtocol
from .trading import StrategyExchangeProtocol, TradingBrokerProtocol

__all__ = [
    "BrokerProtocol", "ReplayBrokerProtocol", "DataFeedProtocol",
    "EngineProtocol", "ResultProtocol", "OrderProtocol", "OrderSnapshot",
    "PnlProtocol", "Config", "FeedFactory", "BrokerFactory",
    "TradingBrokerProtocol", "StrategyExchangeProtocol",
]
