# 薄配置运行入口

状态：已实施，入口为 `minbt.run` 函数；现有 Exchange 手工装配继续有效。

## 1. 签名

```python
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Type, Union

from minbt.protocols.broker import BrokerProtocol
from minbt.protocols.data import DataFeedProtocol
from minbt.protocols.engine import EngineProtocol
from minbt.protocols.result import ResultProtocol
from minbt import Strategy

Config = Mapping[str, Any]
FeedFactory = Callable[[Config], Iterable[DataFeedProtocol]]
BrokerFactory = Callable[[Config], BrokerProtocol]

def run(
    strategy_class: Type[Strategy],
    config: Union[str, Path, Config],
    *,
    feed_factory: FeedFactory,
    broker_factory: Optional[BrokerFactory] = None,
    engine: Optional[EngineProtocol] = None,
    control: Optional[Callable[[], str]] = None,
) -> ResultProtocol:
    ...
```

默认运行只需：读取 JSON、调用用户 Feed 工厂、创建配置中的默认 Broker、构造策略、
调用 Exchange.add_feed/add_strategy/run，并返回已有 RunResult。外部引擎返回其符合协议的冻结结果。

不新增配置编译器、运行容器、插件注册表、策略实例池或另一套生命周期。JSON 用标准库读取；
没有必要依赖配置校验库或同时支持多个文件格式。

## 2. 用户数据的配置

```json
{
  "strategy": {
    "id": "demo",
    "params": {"symbol": "ASSET_X"}
  },
  "data": {
    "path": "prepared/my-data.csv"
  },
  "broker": {
    "initial_cash": 1000,
    "fee_rate": 0
  },
  "run": {
    "start": "2026-01-01",
    "end": "2026-02-01",
    "load_mode": "auto"
  }
}
```

data 是用户工厂的配置，核心不解释其中的业务字段，也不要求数据为某种市场或特定文件格式。
路径的存在与格式由工厂校验，核心不打开文件后猜测列名和数据服务。以上路径仅为自备文件例子。

调用工厂时传入各自配置切片：feed_factory(config["data"])，broker_factory(config["broker"])。
默认 Broker 接收原构造参数；broker=null 表示纯信号实验，不创建账户。缺少必要账户参数时明确失败。

strategy 使用现有 ID/params 构造；省略 ID 时使用策略类名，params 缺省为空字典。
run 映射到当前运行参数，load_mode 是默认 Exchange 的选择，
其他引擎显式校验其支持的选项。未知顶层字段失败，用户 data 内的字段由自己的工厂解释。

## 3. 独立工厂

用户可在自己项目里准备代码：

```python
def build_my_feeds(data_config):
    return [MyFileFeed(data_config["path"])]

def build_my_broker(broker_config):
    return MyBroker(**broker_config)

result = run(
    MyStrategy,
    "config.json",
    feed_factory=build_my_feeds,
    broker_factory=build_my_broker,
)
```

工厂可以使用用户预先读取的行、文件或自己的数据库，返回 Feed 列表或生成器；底层依赖属于用户
实现。不要在库中注册用户代码，配置文件也不保存任意 Python 对象和回调。

入口只按调用时工作目录定位 config.json；数据路径的解释属于用户工厂。以上示例也按工作目录定位
自备文件。需要其他基准时，用户在 data 中显式提供自己的 root 或使用绝对路径；核心不改写任意字符串。

工厂为每次运行创建新资源。默认入口沿用原关闭、异常优先和只读控制语义；创建失败也释放此前成功
创建的对象。Feed 在启动后由 Exchange 关闭，装配/预检失败时由入口关闭，避免重复释放；
入口还关闭带 close 的 Broker 和工厂迭代器。关闭失败不覆盖原异常，正常收尾失败仍抛出。
异步、实时和外部引擎的特殊初始化不强塞进此函数。

完整自备数据与文件参数示例见 [18_config_run.py](../../../examples/18_config_run.py) 和
[18_config_run.json](../../../examples/18_config_run.json)。

## 4. 输出与信息记录

默认只返回 RunResult；用户自行决定是否绘图、保存或分析。不自动创建目录、下载数据、上传报告或
同步资料。配置和数据描述可作为结果的可选元信息，用户可提供数据版本或指纹，核心不扫描全数据。

先实现当前结果查询的协议。保存格式、完整复现等级与大数据输出等有真实需要时单独设计，
不为了一个 run 简写增加多表存储系统。
