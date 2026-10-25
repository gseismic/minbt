# minbt 小内核与自定义数据设计稿

## 状态与最新约束

当前边界按 [PLAN-065](../dev/PLAN-065-core-broker-no-compatibility.md) 修正：默认模拟交易归回核心，删除历史转发。
版本仍为 minbt `0.1.1`；最新验收见 [实施结果](../dev/PLAN-065-core-broker-no-compatibility-OUTCOME.md)。

本版以用户最新要求为准：保留 mini 属性；数据全部由用户准备；默认 Broker 属于核心；不保留历史兼容层。
数据读取与特殊市场扩展放入 `minbt.plugins`，不把市场识别、数据获取和插件管理做成核心职责。

可替换性通过协议与工厂实现，不意味着默认基础能力必须放入 plugins。

## 1. 收敛结论

保留现有模型：

```text
用户准备的数据 → Feed → Exchange → Strategy ↔ Broker → RunResult
```

当前阶段只做三件事：

1. 集中已有协议，补齐 Exchange 实际使用的 Broker 方法。
2. 将具体数据读取放入 plugins，通用模拟交易实现直接归属核心 broker。
3. 沿用 RunResult 的快照与查询，定义供绘图使用的结果协议；增加薄 run 入口。

两层扩展仍有意义，但它们是两个接口边界，不是两套必须新建的框架：

| 边界 | 最小职责 | 当前做法 |
| --- | --- | --- |
| 运行引擎 | 运行策略并返回标准结果 | 直接复用 Exchange；其他引擎有真实接入需求时才写适配器 |
| 数据与交易实现 | 读取用户数据、执行交易和查询状态 | 自定义 Feed/Broker 直接注入，可独立组合 |

数据格式与交易模型分开。同一份用户数据可以配不同 Broker，同一 Broker 可以配不同 Feed。
不要求“一个市场包必须同时创建数据和账户”，也不要求用户先注册一个市场名称才能回测。

## 2. 哪些设计会让核心膨胀

若将上一稿中的全套注册表、市场组合绑定、BrokerRouter、运行阶段对象、成交报告管线、全部结果表和
持久化存储一起实现，核心职责和概念数量都会增长。本版撤回这些作为当前必需项的安排。

| 内容 | 本版处理 |
| --- | --- |
| 全局插件注册表、名称发现、引擎/市场组合矩阵 | 不实现；Python 显式导入和对象/工厂注入即可 |
| 通用交易后端、命令转换和两份订单状态 | 不实现；Broker 直接提供现有方法并拥有账本 |
| 默认跨账户 Router、多币种换算 | 不增加；已有路由行为保留，新增能力按真实需求独立设计 |
| 新生命周期框架、通用事件总线 | 不增加；复用当前单次运行、控制、资源清理和具名回调 |
| 大型结果记录/存储管线 | 不增加；先标准化现有 RunResult 查询 |
| 数据下载、同步、清洗、复权或市场日历推断 | 用户负责准备，核心不获取或猜测 |
| 真实规则、费用、结算等新增金融模型 | 由具体 Broker 扩展，不进入 Exchange |
| 各种外部引擎的预设适配器 | 不预建；定义入口边界，接入实际引擎时再验证 |

## 3. 用户接口与唯一入口

核心提供构造、回调、下单、历史查询和运行控制，包含：

- `Strategy/Broker/Exchange/Order/Market/Pnl/RunResult` 原入口；
- `set_bars/set_books/set_trades/set_news/add_feed/add_strategy/run`；
- `on_init/on_bars/on_books/on_trades/on_news/on_bar/on_finish`；
- `self.broker` 的交易、退出、分仓和查询方法；
- 读取模式、价格选择和已有规则预设。

具体读取器从 `minbt.plugins.binance.feed` 或 `minbt.plugins.storage` 导入，协议从 `minbt.protocols` 导入；
不保留旧数据模块、兼容导出或模块别名。根包仍导出常用核心对象，这是正式的便捷入口。

实现迁移不能顺带改变回调次数、成交时点、费用或原账户口径。最小示例继续直接使用当前 API：

```python
from minbt import Bar, Broker, Exchange, Strategy

class MyFeed:
    name = "my-data"

    def events(self):
        yield Bar("2026-01-01", "ASSET_X", "kline", {"close": 100})
        yield Bar("2026-01-02", "ASSET_X", "kline", {"close": 120})

class MyStrategy(Strategy):
    def on_bars(self, dt, bars):
        self.broker.order_target_size("ASSET_X", 1)

broker = Broker(initial_cash=1_000)
strategy = MyStrategy("demo", broker=broker)
exchange = Exchange()
exchange.add_feed(MyFeed())
exchange.add_strategy(strategy)
result = exchange.run()
curve = result.get_equity_curve()
```

这个例子使用当前已实现接口，没有市场库或数据服务依赖。用户也可以直接把自己准备的列表或表格
传给 `exchange.set_bars(data)`。自定义 Broker 负责自己的交易与记账，不要求继承某个市场类。

## 4. 配置入口可以很薄

新增入口的目标是减少重复装配，不代替原手工路径：

```python
result = run(
    MyStrategy,
    "config.json",
    feed_factory=build_my_feeds,
)
```

`build_my_feeds(config["data"])` 由用户实现，返回自己的 Feed 序列；库不解释这些数据的业务含义。
默认 Broker 使用配置中的已有构造参数；需要自定义 Broker 时显式传 `broker_factory=`。

如果选择其他引擎，可以显式传 `engine=my_adapter`。第一版不从配置字符串扫描或加载任意模块，
也不建立注册表。没有外部引擎需求时，run 只是读取配置、创建对象、调用原 Exchange 的小函数。

配置文件负责参数，工厂负责用户代码和资源。文件本身不执行 Python，不把活对象或任意回调序列化。

## 5. 最小目录与依赖

```text
minbt/
  protocols/
    data.py          # 现有 Feed/数据记录契约
    broker.py        # 现有交易接口及回放推进方法
    engine.py        # 薄运行入口的扩展契约
    result.py        # 现有结果查询契约
  plugins/
    binance/         # 实盘 Broker/Exchange；feed/ 放历史读取实现
    storage/         # 已有通用文件/数据库读取实现
  exchange.py        # 保留唯一默认回放实现
  strategy.py        # 保留原策略基类
  broker/            # 默认模拟账户、订单、持仓、盈亏、撮合和退出的唯一实现
  data/              # 数据模型、批次和基础 Feed，直接服务默认回放
  result.py          # 保留现有 RunResult 实现
  run.py             # 薄配置入口，直接调用原 Exchange
```

不为目录整齐而新增 core 包，也不为每个步骤创建类。plugins 承载扩展功能，不代表每个模块需要
插件基类、注册对象或插件管理器。用户的自定义 Feed/Broker 可以保存在用户项目内，直接导入使用。

默认 Broker 是本库回测的基础能力，属于核心。特殊交易/财务模型可替换 Broker，或复用核心组件；
核心不反向导入插件。默认自备数据实验从导入到结果均无需加载 plugins。

协议只依赖标准库和其他协议记录，不导入数据 SDK 或绘图库。当前安装依赖先保持不变，不新增数据服务
依赖。每项实现只有一个正式归属，删除旧数据转发模块和模拟交易兼容别名。

现有 Binance 文件格式仍可由用户自行准备后读取；插件保留已有显式下载能力，核心及新配置入口不自动
选择下载、联网补齐或创建缓存。数据准备不是本库运行的前置自动任务。

## 6. 需要补齐的真实边界

| 当前情况 | 最小调整 |
| --- | --- |
| BrokerProtocol 定义在 strategy.py | 集中到 protocols，由调用处直接引用 |
| Exchange 调用协议外 process_market_batch | 补充回放侧方法声明，不增加另一套交易后端 |
| Feed 生命周期和排序能力散落实现 | 文档集中约定，name/events 最小接口保留 |
| 结果快照要求具体 Order/Pnl | 验证标准字段并复制，避免要求插件继承具体实现 |
| 运行保护特殊识别内置 Broker | 保留当前行为，逐步复用已有保护代码，不新增公开阶段框架 |
| Strategy 与 Exchange 有历史重复记录 | 可局部整合，但不能再并行增加 Recorder/Observer 管线 |

当前 Strategy 基类已经提供空回调与历史查询，继续复用它。不为了“完全鸭子类型”再建设一套策略容器
和调度系统；其他引擎的策略桥接等实际适配时再做。

## 7. 如何衡量核心增量

协议声明不是运行逻辑，但它仍然是代码。薄 run 和少量校验也会新增行数。
**按职责确定核心，不通过搬动基础账户代码制造核心变小的数字。**

本次实施结果区分：

- 原有代码移动了多少，不能把移动算成新增功能；
- 协议、薄入口新增多少，删除转发层减少多少；
- 运行分支、依赖和需要用户理解的概念是否增加；
- 示例导入是否指向唯一入口，数据与金融结果是否保持一致。

约束是：不增加第二个回放主循环；不在核心放数据获取、特殊市场业务或通用插件管理；
同一行为只保留一份实现。只有协议与薄装配代码增长，不构成向核心追加市场功能的理由。

PLAN-064 的 399 行增量与 simulation 布局属于前一阶段记录；当前去除兼容层后的规模与验证，
以 PLAN-065 实施结果为准。默认账户归回核心属于重新划分归属，没有增加一套模拟实现。

## 8. 实施顺序

1. 集中已有接口声明，补齐实际回放依赖，直接引用唯一协议。
2. 读取实现位于 plugins；默认模拟实现位于 broker；清理全部历史转发。
3. 保持现有结果查询、配置入口和金融行为，并验证核心独立于插件。
4. 外部引擎、复杂金融模型和持久化格式在实际使用需求出现时单独推进。

用户已授权按最新边界调整，验收状态见 PLAN-065。详情见 [协议目录](protocols/README.md)。
本稿采用用户最新约束；旧设计中删除公开回调或扩大框架的安排不作为本轮实施依据。
