"""用用户提供的工厂装配一次实验，复用既有 Exchange。"""

from collections.abc import Mapping
from copy import deepcopy
import json
from pathlib import Path
from typing import Callable, Optional, Type, Union

from .broker import Broker
from .exchange import Exchange
from .protocols.broker import ReplayBrokerProtocol
from .protocols.engine import BrokerFactory, Config, EngineProtocol, FeedFactory
from .protocols.result import ResultProtocol
from .strategy import Strategy


def _load_config(config) -> dict:
    """只读取参数，复制调用方配置；用户数据字段由自己的工厂解释。"""

    if isinstance(config, (str, Path)):
        with Path(config).open(encoding="utf-8") as stream:
            config = json.load(stream)
    if not isinstance(config, Mapping):
        raise TypeError("config must be a JSON object, Mapping, or JSON file path")
    unknown = set(config) - {"strategy", "data", "broker", "run"}
    if unknown:
        raise ValueError(f"unknown config fields: {sorted(map(str, unknown))}")
    config = deepcopy(dict(config))
    for name in ("strategy", "data", "run"):
        config.setdefault(name, {})
        if not isinstance(config[name], Mapping):
            raise TypeError(f"config.{name} must be a Mapping")
        config[name] = dict(config[name])
    config.setdefault("broker", {})
    if config["broker"] is not None and not isinstance(config["broker"], Mapping):
        raise TypeError("config.broker must be a Mapping or null")
    if set(config["strategy"]) - {"id", "params"}:
        raise ValueError("config.strategy only accepts id and params")
    params = config["strategy"].get("params", {})
    if not isinstance(params, Mapping):
        raise TypeError("config.strategy.params must be a Mapping")
    config["strategy"]["params"] = dict(params)
    if "id" in config["strategy"] and (
        not isinstance(config["strategy"]["id"], str) or not config["strategy"]["id"].strip()
    ):
        raise ValueError("config.strategy.id must be a non-empty string")
    if set(config["run"]) - {"start", "end", "load_mode"}:
        raise ValueError("config.run only accepts start, end and load_mode")
    return config


def run(
    strategy_class: Type[Strategy],
    config: Union[str, Path, Config],
    *,
    feed_factory: FeedFactory,
    broker_factory: Optional[BrokerFactory] = None,
    engine: Optional[EngineProtocol] = None,
    control: Optional[Callable[[], str]] = None,
) -> ResultProtocol:
    """创建新实验并返回独立结果，数据准备和读取完全交给调用方。

    工厂分别收到 data/broker 参数字典，每次须创建新的对象。broker=null 时不创建账户；
    未提供 broker_factory 时使用原 Broker 构造。外部引擎负责调用工厂和冻结自己的结果。
    配置文件和数据工厂中的相对路径均由调用方按工作目录或显式根目录解释。
    """

    if not isinstance(strategy_class, type) or not issubclass(strategy_class, Strategy):
        raise TypeError("strategy_class must be a Strategy subclass")
    for name, factory in (("feed_factory", feed_factory), ("broker_factory", broker_factory), ("control", control)):
        if (factory is not None or name == "feed_factory") and not callable(factory):
            raise TypeError(f"{name} must be callable")
    config = _load_config(config)
    if engine is not None:
        if not isinstance(engine, EngineProtocol) or not callable(engine.run):
            raise TypeError("engine must implement EngineProtocol.run()")
        result = engine.run(
            strategy_class, config, feed_factory=feed_factory,
            broker_factory=broker_factory, control=control,
        )
        if not isinstance(result, ResultProtocol) or not isinstance(result.meta, Mapping):
            raise TypeError("engine.run() must return an independent ResultProtocol")
        return result

    exchange = Exchange()
    feeds = []
    broker = producer = None
    try:
        if config["broker"] is not None:
            broker = Broker(**config["broker"]) if broker_factory is None else broker_factory(config["broker"])
            if not isinstance(broker, ReplayBrokerProtocol) or not callable(broker.process_market_batch):
                raise TypeError("broker_factory must return a ReplayBrokerProtocol")
        producer = iter(feed_factory(config["data"]))
        for feed in producer:
            feeds.append(feed)
            exchange.add_feed(feed)
        options = config["strategy"]
        strategy = strategy_class(
            strategy_id=options.get("id", strategy_class.__name__),
            broker=broker, params=options["params"], logger=exchange.logger,
        )
        exchange.add_strategy(strategy)
        return exchange.run(control=control, **config["run"])
    finally:
        # 启动后 Feed 已由 Exchange 关闭；装配/预检失败时仍由本入口释放。
        resources = [broker, producer]
        if exchange._run_state == "ready":
            resources.extend(feeds)
        else:
            resources = [item for item in resources if all(item is not feed for feed in feeds)]
        unique = {id(item): item for item in resources if item is not None}
        exchange._close_resources(list(unique.values()), label="configuration resources")


__all__ = ["run"]
