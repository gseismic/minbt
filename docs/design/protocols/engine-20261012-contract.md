# 最小运行引擎扩展契约

状态：EngineProtocol 与显式注入已实施。默认引擎仍是 Exchange，未内置外部引擎 SDK。

## 1. 两层是接口边界

第一层约定策略运行的输入与标准结果；第二层通过用户 Feed/Broker 提供数据和交易行为。
它们不要求新增两套容器、注册表或管理框架。

默认入口直接复用现有 Exchange。无需先实现一个公开 ExchangeEngine 类再包住它；一个私有装配
函数即可。未来确实接入不同引擎时，才增加该引擎的适配器。

## 2. 可选引擎协议

下面是薄入口与外部适配器的边界，Exchange.run 保留原签名：

```python
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol, Type

from minbt.protocols.broker import BrokerProtocol
from minbt.protocols.data import DataFeedProtocol
from minbt.protocols.result import ResultProtocol

Config = Mapping[str, Any]
FeedFactory = Callable[[Config], Iterable[DataFeedProtocol]]
BrokerFactory = Callable[[Config], BrokerProtocol]

class EngineProtocol(Protocol):
    def run(
        self,
        strategy_class: Type[Any],
        config: Config,
        *,
        feed_factory: FeedFactory,
        broker_factory: Optional[BrokerFactory] = None,
        control: Optional[Callable[[], str]] = None,
    ) -> ResultProtocol:
        ...
```

策略类默认遵循现有 Strategy 构造和回调约定。特殊构造继续使用原手工装配，不为覆盖所有构造签名
建设另一套策略工厂框架。实际外部适配器有必要时可提供自己的显式扩展。

默认执行和所选适配器接受同样的输入。默认返回公共 RunResult；外部适配器返回已经冻结的 ResultProtocol
实现，不把活引擎、连接或账户放入结果。查询契约不足以枚举并重新缓存所有历史，核心不增加这种转换框架。
协议仅声明运行/结果边界，不强迫其他引擎使用 Exchange 的内部类型。

## 3. 显式注入即可

```python
result = run(
    MyStrategy,
    "config.json",
    feed_factory=build_my_feeds,
    engine=my_engine_adapter,
)
```

适配器由调用方显式创建；配置文件不扫描模块、不执行代码。
不新增插件发现、引擎名称注册和市场支持矩阵。用户自行选择已配好的实现组合。

其他引擎如果有原生账本，Broker 桥接只操作其真实账户；不能再用默认 Broker 模拟一次并拼接余额。
“可以适配其他引擎”不表示所有引擎无需适配即可执行所有策略。

不支持的回调、控制或交易行为明确拒绝，不能静默改变 pause、pending 或成交时点。只有真实引擎
接入时才固定其需要的能力声明，不先把能力协商系统加进默认回放核心。

## 4. 生命周期与实施边界

每次默认运行创建新的策略、Feed、Broker 和 Exchange。现有单次使用、控制、结束快照和资源清理
继续有效；用户工厂负责为新实验提供新对象，不擅自复制活连接或复用已经执行的账户。

同批次共享账户、回调顺序和结果冻结沿用已有行为。外部适配器自行关闭自有资源、映射原生异常和
标准结果。当前阶段只固定必要边界，不增加预设外部 SDK、空实现或新的调度主循环。

总设计与成本约束见 [小内核设计](../kernel-20261012-protocol-plugins.md)。
