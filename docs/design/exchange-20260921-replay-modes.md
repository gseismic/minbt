# Exchange 回放、通用 Bar 与 Broker 估值设计

## 状态

本文是当前开发实现的设计与接口契约。实现阶段不保留旧事件包装、历史读取参数或由
Exchange 猜测价格的兼容层。

目标是让 mini 回测只保留必要概念：

1. Exchange 负责历史数据的读取、排序、时间批次和分发。
2. Bar 只表示市场观测，不决定账户如何估值。
3. Feed 优先级只决定数据处理顺序。
4. Broker 或用户显式决定盈亏、保证金和订单触发所使用的价格。
5. CSV、iosql 是具体读取来源，不抽象成 Storage、Schema 或 Adapter 层。
6. `ReplayCursor` 和 `TimeBatch` 是 Exchange 内部结构。
7. `stream` 只保留给未来实时模式；历史读取方式使用“全量预加载”和“渐进回放”。

用户门面与内部实现分层：普通 Kline 用户不需要理解回放能力、TimeBatch 或高级估值选择；
这些能力由默认值和进阶配置承载。通用 Bar 的存储格式也不等同于 Kline 格式。

## 1. 用户接口

### 1.1 最短路径

```python
from minbt import Broker, Exchange, Strategy


class MyStrategy(Strategy):
    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["close"]
        self.broker.order_target_percent("BTCUSDT", 0.8, price=price)


exchange = Exchange()
exchange.set_bars(rows)

broker = Broker(initial_cash=10_000, fee_rate=0.001)
exchange.add_strategy(MyStrategy(strategy_id="demo", broker=broker))
exchange.run()
```

用户需要理解的对象只有：

|对象|职责|
|---|---|
|`Exchange`|注册数据、按时间回放、调用 Broker 和 Strategy|
|具体 Feed|从内存、CSV、iosql 或其他来源提供历史事件|
|`Strategy`|读取回调数据，产生交易意图|
|`Broker`|选择估值价格，维护订单、持仓、盈亏和风险|

用户不创建 `ReplayCursor`、`TimeBatch`、Storage、Schema 或 Adapter。

### 1.2 Exchange 入口

```python
exchange.set_bars(data, date_key="dt", symbol_key="symbol", feed_priority=0)
exchange.set_books(data, date_key="dt", symbol_key="symbol", feed_priority=0)
exchange.set_trades(data, date_key="dt", symbol_key="symbol", feed_priority=0)
exchange.set_news(data, date_key="dt", symbol_key="symbol", feed_priority=0)

exchange.add_feed(feed, feed_priority=10)
exchange.add_strategy(strategy)

exchange.run()
exchange.run(load_mode="auto")
exchange.run(load_mode="preload")
exchange.run(load_mode="incremental")
```

`set_*` 是已经在内存中的行数据的最短入口；`add_feed` 用于自定义读取来源。`feed_priority` 的
默认值为 `0`，数值越大越早进入同一时间批次的分发流程。

普通用户只需要 `exchange.run()`；显式 `load_mode` 用于进阶的内存/速度控制。

### 1.3 Strategy 回调

```python
class MyStrategy(Strategy):
    def on_init(self):
        ...

    def on_bars(self, dt, bars):
        ...

    def on_bar(self, dt, bar):
        ...

    def on_books(self, dt, books):
        ...

    def on_trades(self, dt, trades):
        ...

    def on_news(self, dt, news):
        ...

    def on_finish(self):
        ...
```

Exchange 固定按以下事件族分发：

```text
on_bars → on_books → on_trades → on_bar → on_news
```

同一 Feed 同一时间点的同类数据会合并到一次回调中；多个 Feed 的同类数据分别回调，避免
重叠数据被静默覆盖。

## 2. 市场数据模型

### 2.1 Bar

```python
Bar(
    dt=datetime,
    symbol="BTCUSDT",
    kind="kline",
    data={"close": 100.0},
)
```

Bar 表示一个时间点、一个 symbol 的市场观测。必需字段只有：

|字段|含义|
|---|---|
|`dt`|UTC 时间，内部统一到毫秒精度|
|`symbol`|非空标的名称|
|`kind`|数据分类|
|`data`|该分类自己的只读数据载荷|

Bar 不包含 `price`、`price_priority` 或 `mark_price`。这些属于 Broker 的账户规则，不属于
市场观测。

`data` 在 Bar 创建时递归冻结常见的字典、列表、元组和集合。Bar 外层不可变，策略回调期间
只能读取数据；策略如果主动保存数据，额外内存由策略承担。

### 2.2 内置 kind

```text
kline
orderbook
trade
price
```

Kline 是 Bar 的一种，不强制完整 OHLCV：

```python
Bar(dt, "A", "kline", {"close": 100.0})
```

OrderBook 也可以是 Bar：

```python
Bar(
    dt,
    "A",
    "orderbook",
    {"bids": [(100.0, 1.2)], "asks": [(100.1, 0.8)]},
)
```

第一阶段只要求 OrderBook 来源提供完整快照，不处理需要序号、校验和及快照恢复的增量盘口。

Trade 和只提供价格的 Bar 也不要求 OHLCV：

```python
Bar(dt, "A", "trade", {"price": 100.0, "qty": 0.1, "side": "buy"})
Bar(dt, "A", "price", {"value": 100.2, "source": "exchange_mark"})
```

用户可以增加自定义 kind。Exchange 不为未知 kind 自动创建 Schema 或专用策略回调，统一通过
`on_bar` 传递原始 Bar。

### 2.3 News

```python
News(
    dt=dt,
    symbol=None,
    data={"headline": "...", "sentiment": 0.4},
)
```

News 不是 Bar，因为它不要求 symbol，也没有必须用于收益计算的价格。News 默认不会：

- 更新 Broker 市场价格。
- 参与浮动盈亏。
- 触发价格相关订单。

News 可以有可选 `symbol`，多标的关联信息放入 `data`。

## 3. Feed 契约

用户可以直接使用 Binance Kline 专用的 `BinanceKlineCsvFeed`、`BinanceKlineIosqlFeed`、
`binance.BinanceKlineFeed`，也可以使用通用 `CsvBarFeed`、`IosqlBarFeed` 或实现自己的历史 Feed。
Feed 输出必须直接是 `Bar | News`：

```python
class MyFeed:
    name = "my-feed"

    def prepare(self):
        ...

    def events(self):
        yield Bar(...)

    def close(self):
        ...
```

普通 Feed 只需要提供 `name` 和 `events()`；缺省按“可全量预加载、可能无序、不支持渐进回放、可重复读取”
处理。CSV、iosql 等已知有序来源会额外声明渐进回放能力。

属性含义：

- `supports_preload`：是否可以先读取全部有限历史事件。
- `supports_incremental`：是否可以按时间逐步读取。
- `ordered`：`events()` 是否按非递减 `dt` 产生事件。
- `replayable`：每次运行能否重新获得等价事件序列。
- `prepare()` 和 `close()`：来源资源的生命周期管理；`close()` 必须幂等。

Feed 不负责：

- 选择盈亏价格。
- 计算收益和保证金。
- 处理订单。
- 合并多个来源的时间轴。

CSV、iosql 只是读取实现，不能改变 Bar 的语义。

通用 Bar 存储使用最小信封：

```text
dt + symbol + kind + data
```

CSV 中 `data` 为 JSON 文本；iosql 中 `dt` 为 UTC 毫秒时间戳、`data` 为 JSON 文本。Kline 专用
CSV/iosql 表仍可使用专用便利 Feed，但不代表 Bar 只能是 Kline。

## 4. Exchange 的职责边界

### 4.1 Exchange 负责

1. 接收内存数据和历史 Feed。
2. 把时间统一为 UTC 毫秒精度。
3. 对内存数据排序并检查同类唯一性。
4. 对多个有序来源做 k 路归并。
5. 收集同一 `dt` 的全部事件并构造 `TimeBatch`。
6. 按 `(事件族、-feed_priority、注册顺序、来源序号)` 排序。
7. 把完整批次交给每个唯一 Broker。
8. 按回调族和 Feed 顺序调用 Strategy。
9. 在正常、异常和来源耗尽时释放 Feed 资源。

### 4.2 Exchange 不负责

1. 从 `close`、`mid`、`last` 中猜测账户估值价格。
2. 计算浮动盈亏、组合保证金或强平。
3. 决定限价单触发价格。
4. 把 Feed 优先级当成价格优先级。
5. 为每个自定义 Bar kind 增加一组 API。

## 5. 排序与同一时间批次

### 5.1 排序键

不同来源先按 `dt` 做全局归并。同一 `dt` 内使用：

```text
(event_family_order, -feed_priority, feed_registration_index, source_sequence)
```

事件族顺序为：

```text
kline → orderbook → trade → custom(on_bar) → news
```

自定义 Bar 会通过 `on_bar` 逐条进入策略回调，排序位于 Trade 之后、News 之前；它也会保留
在 TimeBatch 中供 Broker 使用。

### 5.2 同优先级 Feed

同优先级不是错误。规则是：

1. 同优先级按注册顺序稳定处理。
2. 不同事件族即使优先级相同，也不 Warning。
3. 同一 `dt`、同一事件族、同一 symbol 且来自不同同优先级 Feed 时 Warning。
4. Warning 不丢弃事件，也不自动覆盖数据。
5. 如果 Broker 选定的估值来源出现多条候选，按 Broker 的聚合规则处理；默认报错。

Feed 优先级只影响处理顺序，不影响估值来源选择。

### 5.3 TimeBatch

```text
TimeBatch(
    dt=dt,
    items=(
        (feed_name, feed_priority, registration_index, sequence, Bar | News),
        ...,
    ),
)
```

生命周期：

```text
读取各来源头部
  → 收齐同一 dt
  → 构造 TimeBatch
  → Broker 选择估值并批量更新
  → Broker 处理挂单、退出和风险
  → Exchange 分发 Strategy 回调
  → 记录历史
  → 释放 Exchange 对当前批次的引用
```

TimeBatch 的内存与当前时间批次、各 Cursor 头部和底层读取缓冲有关，不承诺严格常数。大量
Trade 使用相同时间戳时，单个批次本身可以很大。

## 6. ReplayCursor 与回放模式

`ReplayCursor` 是 Exchange 内部对 Feed 的读取包装，用户不创建它。它负责统一来源名称、
优先级、能力、来源序号和生命周期，不解释市场字段。

### 6.1 全量预加载

适合小数据和速度优先：

```text
读取全部有限事件
  → 必要时排序
  → 按 TimeBatch 回放
```

历史行情内存随事件总量增长。

### 6.2 渐进回放

适合 CSV、iosql 等有序来源：

```text
各 Cursor 保留一个头部
  → k 路归并
  → 当前 TimeBatch
  → 处理并释放当前批次
```

内存主要与当前批次、来源数量和读取缓冲相关，时间复杂度为 `O(E log K)`，其中 `E` 是事件
数，`K` 是来源数。

### 6.3 自动选择

```python
exchange.run(load_mode="auto")
```

选择规则：

1. 所有来源支持渐进回放且有序时，优先渐进回放。
2. 否则所有来源支持全量预加载时，选择全量预加载。
3. 没有共同可用模式时，在策略回调开始前报错并列出能力。
4. 不在运行中隐式切换模式或重复读取。
5. `set_*` 数据本身已经在内存中，不能因为选择渐进回放而消除这部分内存。

显式模式不支持时立即报错：

```python
exchange.run(load_mode="preload")
exchange.run(load_mode="incremental")
```

## 7. Broker 估值与账户更新

### 7.1 估值来源

Broker 的最小配置：

```python
Broker(
    initial_cash=10_000,
    mark_price="kline.close",
)
```

也可以使用常见的简写：

```python
mark_price="orderbook.mid"
mark_price="trade.price"
mark_price="price.value"
```

默认值为 `"kline.close"`。高级场景仍可使用精确 Feed 路由或 callable，但不属于普通用户的主路径。

### 7.2 多候选与缺失

```python
Broker(
    initial_cash=10_000,
    mark_price="trade.price",
    mark_price_aggregation="last",
)
```

`mark_price_aggregation` 支持 `error`、`first`、`last` 或接收价格序列的函数。默认 `error`，
不让 Broker 猜测多条数据的含义。缺失当前价格时，如果已有上一价格可以继续沿用；如果账户已有
持仓或订单且从未获得过价格，Broker 会报错并说明当前估值规则和修复方式。

没有配置估值来源的 Bar 不会自动参与盈亏。News 永远不自动参与估值。

### 7.3 批量推进

Broker 对每个 TimeBatch 只推进一次：

```text
选出所有 symbol 的 mark price
  → 更新所有 Position 的未实现盈亏
  → 统一计算组合保证金
  → 处理强平和风险
  → 处理 pending order 与退出条件
```

不能按 symbol 顺序逐个调用市场价格更新，否则跨标的全仓组合的结果会依赖更新顺序。

mini 版本暂时可以让一个选出的价格同时用于估值、挂单触发、退出条件和没有显式价格的订单
参考。未来如果需要更真实的成交模拟，再在 Broker 内拆分 `mark_price`、`trigger_price` 和
`execution_price`，不扩展 Bar 字段。

## 8. 回调投影

已知数据族使用稳定的专用回调；未知 kind 使用通用 `on_bar(dt, bar)`，不要求 Exchange 为每个
新 kind 增加一组 API：

|事件|策略回调|回调数据|
|---|---|---|
|`kind="kline"`|`on_bars`|`symbol -> data`|
|`kind="orderbook"`|`on_books`|`symbol -> data`|
|`kind="trade"`|`on_trades`|`symbol -> data 列表`|
|`kind="price"` 或自定义 kind|`on_bar`|单个只读 `Bar`|
|`News`|`on_news`|`News` 对象序列|

Broker 仍然可以独立使用自定义 Bar 作为估值来源；`on_bar` 只负责把原始 Bar 交给 Strategy，
不解释其 `data` 字段。

## 9. 生命周期、错误与性能

### 9.1 来源生命周期

正常结束、数据异常、策略异常和 Broker 异常都必须调用 Feed 的 `close()`。关闭操作幂等，
关闭异常不能覆盖正在传播的原始业务异常。

### 9.2 主要错误

- Feed 输出不是 `Bar | News`：类型错误。
- 渐进来源时间回退：立即报错并指出来源和时间。
- Kline 或完整 OrderBook 同一来源同一时间同一 symbol 重复：报错。
- 回放能力不满足 `load_mode`：列出来源能力。
- 估值字段不存在、非有限正数或多候选无法聚合：Broker 报错。
- 非 `replayable` 来源重复运行：提前报错。

### 9.3 性能边界

- 内存数据入口会在注册时排序和冻结数据，便于快速回放。
- 全量预加载的历史行情内存为 `O(E)`。
- 渐进回放的 Exchange 内存为 `O(B + K + R)`，`B` 是当前批次，`K` 是来源头部数量，`R`
  是底层读取缓冲。
- 多来源时间归并为 `O(E log K)`。
- Strategy 保存 Bar 数据产生的内存不计入 Exchange 的回放内存。

## 10. 实时模式边界

本设计不实现实时模式。未来可以单独提供：

```python
exchange.run_live(source)
```

实时模式需要另外定义迟到事件、水位线、背压、取消、断线重连和停止语义。历史渐进回放不
称为 stream。

## 11. 实施验收

当前代码应满足：

1. `Bar`、`News` 可直接构造，载荷只读。
2. Kline、OrderBook、Trade、Price 和 Custom 不共享 OHLCV 强制校验。
3. CSV、iosql Feed 输出 `Bar`，不输出旧事件对象。
4. Exchange 支持 `auto/preload/incremental` 三种历史回放方式。
5. 同一 `dt` 的所有来源先进入一个 `TimeBatch`。
6. Feed 优先级只影响分发顺序，同优先级真实重叠时 Warning。
7. Broker 根据配置选择估值来源并批量更新组合。
8. News 默认不参与估值。
9. Feed 资源在正常和异常路径都释放。
10. 测试覆盖数据模型、来源能力、排序、重复、估值、批量账户更新和例子。
