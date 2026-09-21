# minbt 用户接口与内核重构设计

## 状态

目标设计，待实施。

本文定义 minbt 下一阶段的稳定用户接口和由此推导出的内部架构。设计优先级是：

1. 普通 Kline 回测必须保持短、直观、容易验证。
2. 多 symbol 是标准模型，单 symbol 是自然特例。
3. OrderBook、Trade、News 在当前设计中正式支持，不作为未来占位能力。
4. 用户接口采用明确的数据类型回调，不暴露内部通用事件模型。
5. 内核只保留“同一时间点收齐后再批量更新”这一必要正确性边界，不把实现步骤扩张成一组框架类。

本文是数据接入、Strategy 回调、价格提取、Exchange 调度和 Broker 批量账户更新的最高优先级设计。
它在这些范围内替代：

- `minbt-20260630-system-design.md` 中的数据接入、Strategy 回调和回测时钟章节；
- `data-feed-20260701-design.md` 中的旧 FeedEvent、事件合并和价格更新设计；
- `exchange-20260921-replay-modes.md` 中公开通用 `Bar.kind`、`on_bar` 和 Broker 直接解释字段的设计。

上述文档中的 Broker 下单、Portfolio、Market、退出条件等未被本文明确修改的部分继续有效。

## 1. 结论摘要

稳定用户接口采用 v0 的分类回调模型：

```python
class Strategy:
    def on_init(self): ...
    def on_bars(self, dt, bars): ...
    def on_books(self, dt, books): ...
    def on_trades(self, dt, trades): ...
    def on_news(self, dt, news): ...
    def on_finish(self): ...
```

明确删除：

```python
def on_bar(self, dt, bar): ...
```

不向普通策略用户公开，也不在内部预设为必须的类：

- `Bar(kind=...)` 通用事件模型；
- `MarketData` 聚合包装对象；
- `TimeBatch`、`BatchItem`、Cursor 和 Feed 能力位；
- `mark_price="kind.field"` 这类把内部字段路径暴露给账户的配置。

Kline 数据不强制字段名为 `close`。用户通过 `price_key` 指定当前数据源中哪个字段可以产生
Broker 的参考价格：

```python
exchange.set_bars(data, price_key="close")
exchange.set_bars(data, price_key="price")
exchange.set_bars(data, price_key="last_price")
exchange.set_bars(data, price_key=None)  # 仅作为信号数据，不更新参考价格
```

`price_key` 只负责“从这个来源的记录中取哪个字段作为参考价”。一次 `run()` 中，同一 symbol
只允许一个来源启用 `price_key`；发现第二个价格来源时直接报错，用户在其他来源上设置
`price_key=None` 即可消歧。不再引入 `PriceCandidate`、`PriceResolver` 或 `price_source`。

### 1.1 v0 与当前实现的取舍

|方案|值得保留|需要修正|
|---|---|---|
|v0|具名 `set_*`、具名回调、`price_key`、一个简单 `_Feed` 记录|内存/流式两套回放路径；按 Feed、按 symbol 多次推进 Broker；`FeedEvent` 与 Feed 重复携带类型|
|当前实现|同一 dt 收齐、Portfolio 批量更新、确定性归并、异常路径资源释放|通用 `Bar.kind`、`on_bar`、`TimeBatch/BatchItem/Cursor`、Broker 解析字段路径，把实现机制变成了用户和维护者概念|
|目标设计|v0 的用户接口和小而直接的数据源模型，加上当前实现已验证的正确性不变式|不承继两边的重复回放路径、通用事件层和字段解析层|

因此目标不是“v0 外壳 + 当前内核全部照搬”，而是保留两边已被用例证明必要的部分。

## 2. 目标与非目标

### 2.1 目标

1. 用户已有 pandas、polars 或 `list[dict]` Kline 时，可以用最少代码完成回测。
2. 单标的和多标的使用同一套回调结构。
3. Kline 可以使用 `close`、`price`、`last_price` 或用户指定的其他价格字段。
4. 支持完整 OrderBook 快照、逐笔 Trade 和 News 数据。
5. 内存数据、CSV、iosql、Binance 和自定义 Feed 对 Strategy 呈现相同接口。
6. 同一时间点的全部 symbol 必须先完成账户批量估值，再执行挂单、退出条件和策略回调。
7. 多来源冲突、价格歧义、缺失字段和空回测必须显式失败，不能依赖默认关闭的日志提醒。
8. 普通用户只需要 `run()`；内存数据与逐行历史 Feed 共用一条调度路径。

### 2.2 非目标

1. 不设计任意 `kind` 的通用事件总线。
2. 不支持用户侧 `on_bar`、`on_event` 或动态生成 `on_{kind}`。
3. 不模拟订单簿队列位置、部分成交和逐笔撮合。
4. 不根据 OHLC 的 high/low 猜测同一根 Kline 内的价格路径。
5. 不实现增量 OrderBook 的序号校验、快照恢复和断档修复；当前只接受完整快照。
6. 不实现实时模式的 watermark、背压、重连和停止协议。
7. 不在一个 `on_bars` 截面中表示同一 symbol、同一 dt 的多个周期或多个竞争 Bar；此类数据应在
   输入前对齐为不同字段，或使用不同回测实例。
8. 不为了兼容当前开发中接口而永久保留错误抽象；迁移期是否提供警告别名由实施计划决定。

## 3. 代表性用户场景

设计按以下场景的频率排序。

### 3.1 单标的 Kline

```python
class SmaStrategy(Strategy):
    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["close"]
        self.prices.append(price)
```

即使只有一个 symbol，回调仍是 `symbol -> row`，不增加单标的结构。

### 3.2 多标的横截面 Kline

```python
class RotationStrategy(Strategy):
    def on_bars(self, dt, bars):
        scores = {
            symbol: row["close"] / row["ma20"] - 1
            for symbol, row in bars.items()
        }
        selected = max(scores, key=scores.get)
        for symbol in bars:
            target = 0.8 if symbol == selected else 0.0
            self.broker.order_target_percent(symbol, target)
```

同一 `dt` 只能收到一次完整 `on_bars`，不能因多个 Feed 被拆成多次部分回调。

### 3.3 非 `close` 价格字段

```python
exchange.set_bars(data, price_key="last_price")

class StrategyUsingLastPrice(Strategy):
    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["last_price"]
        self.broker.order_target_percent("BTCUSDT", 0.5)
```

`last_price` 会作为 Broker 当前参考价格；数据不会被强制改名为 `close`。

### 3.4 只有信号、没有可交易价格的数据

```python
exchange.set_bars(signal_data, price_key=None)
```

数据仍进入 `on_bars`，但不会更新 Broker 参考价格。若策略下单时没有其他来源提供价格，也没有显式
订单价格，Broker 必须立即抛出明确错误。显式订单价格只解决当前这次成交，不会成为可沿用的参考
价格；如果成交后仍没有其他来源持续提供参考价格，后续持仓估值必须报错。因此 `price_key=None`
主要用于只读取信号而不交易，或与另一种有价格的数据类型组合。如果信号和价格都是 bars，应在输入前
合并为同一条 bar，不注册两个相互重叠的 bars Feed。

### 3.5 OrderBook 策略

```python
exchange.set_books(books, price_key="mid")

class BookStrategy(Strategy):
    def on_books(self, dt, books):
        book = books["BTCUSDT"]
        spread = book["asks"][0][0] - book["bids"][0][0]
```

`price_key=None` 时盘口只供策略读取；设置为 `mid` 时可产生 Broker 参考价格。

### 3.6 Trade 策略

```python
exchange.set_trades(trades, price_key="price")

class TapeStrategy(Strategy):
    def on_trades(self, dt, trades):
        rows = trades.get("BTCUSDT", ())
        buy_qty = sum(row["qty"] for row in rows if row["side"] == "buy")
```

同一 `(dt, symbol)` 可以有多笔 Trade。该时间点最后一笔 Trade 的 `price_key` 值成为该 symbol
的参考价格。

### 3.7 News 策略

```python
exchange.set_news(news)

class NewsStrategy(Strategy):
    def on_news(self, dt, news):
        for item in news:
            if item.get("sentiment", 0) > 0.8:
                ...
```

News 可以没有 symbol，也可以使用 `symbol` 或 `symbols` 字段关联一个或多个标的。News 永远不自动
产生参考价格。

### 3.8 多种数据联合使用

数据类型回调顺序固定为：

```text
on_bars -> on_books -> on_trades -> on_news
```

所有数据在任何 Strategy 回调前已按同一时间点收齐，Broker 也已经完成该时间点的批量价格
更新。需要联合数据的高级策略可以按固定顺序保存前序回调状态，并在后序回调中决策；普通 Kline
策略不承担额外包装层。例如 Kline 是交易价格、Trade 只作为信号时：

```python
exchange.set_bars(bars, price_key="close")
exchange.set_trades(trades, price_key=None)
```

### 3.9 大型 CSV / iosql / Binance 数据

```python
exchange.add_feed(feed)
exchange.run()
```

数据读取方式不能改变 Strategy 回调。CSV、iosql 可以逐行产生已排序历史记录，Binance 的下载与
缓存由具体 Feed 自己完成；Exchange 不再暴露回放模式开关。

## 4. 稳定用户模型

普通策略作者只需要理解：

|概念|职责|
|---|---|
|`Exchange`|接收历史数据，按时间组织回放|
|`Strategy`|在明确的数据类型回调中产生交易意图|
|`Broker`|唯一交易入口，维护价格、订单、现金、持仓和风险|
|`Order`|下单结果和退出条件句柄|
|`Market`|需要时配置交易规则；不属于入门必需概念|

稳定主路径：

```python
import pandas as pd

from minbt import Broker, Exchange, Strategy


class DemoStrategy(Strategy):
    def on_init(self):
        self.step = 0

    def on_bars(self, dt, bars):
        if self.step == 0:
            self.broker.order_target_percent("BTCUSDT", 0.8)
        elif self.step == 2:
            self.broker.close_position("BTCUSDT")
        self.step += 1


data = pd.DataFrame([
    {"dt": "2026-01-01", "symbol": "BTCUSDT", "last_price": 100.0},
    {"dt": "2026-01-02", "symbol": "BTCUSDT", "last_price": 110.0},
    {"dt": "2026-01-03", "symbol": "BTCUSDT", "last_price": 120.0},
])

broker = Broker(initial_cash=10_000, fee_rate=0.001)
strategy = DemoStrategy(strategy_id="demo", broker=broker)

exchange = Exchange()
exchange.set_bars(data, price_key="last_price")
exchange.add_strategy(strategy)
exchange.run()
```

普通回调中的市价单、目标仓位和平仓不需要把刚刚收到的价格再次传回 Broker。显式 `price=` 只用于
用户确实需要指定成交价格的场景。

## 5. Strategy 公开接口

### 5.1 目标接口

```python
class Strategy:
    def __init__(
        self,
        strategy_id: str,
        broker: Broker | None = None,
        params: dict | None = None,
        logger=None,
    ) -> None: ...

    def on_init(self) -> None: ...
    def on_bars(self, dt, bars) -> None: ...
    def on_books(self, dt, books) -> None: ...
    def on_trades(self, dt, trades) -> None: ...
    def on_news(self, dt, news) -> None: ...
    def on_finish(self) -> None: ...
```

所有回调在基类中默认是空操作。用户只实现需要的回调。

### 5.2 明确删除

- `on_bar(dt, bar)`；
- `on_data(dt, data)`；
- `on_event(...)`；
- `on_tick(...)`；
- 根据字符串动态寻找任意 `on_{kind}` 的行为。

删除原因：

1. 单条事件回调破坏多 symbol 完整截面的主模型。
2. `on_bar` 与 `on_bars` 名称高度相似，但负载语义完全不同。
3. 已支持的数据类型应该使用领域名称，而不是通过通用 kind 逃生口表达。
4. 未知类型缺少稳定的聚合、重复、价格和错误语义。

### 5.3 回调载荷

bars：

```python
{
    "BTCUSDT": {
        "dt": datetime(...),
        "symbol": "BTCUSDT",
        "last_price": 100.0,
        "volume": 12.3,
        "signal": 0.8,
    },
    "ETHUSDT": {...},
}
```

books：

```python
{
    "BTCUSDT": {
        "dt": datetime(...),
        "symbol": "BTCUSDT",
        "bids": ((100.0, 1.0), ...),
        "asks": ((100.1, 0.8), ...),
        "mid": 100.05,
    }
}
```

trades：

```python
{
    "BTCUSDT": (
        {"dt": datetime(...), "symbol": "BTCUSDT", "price": 100.0, "qty": 0.1},
        {"dt": datetime(...), "symbol": "BTCUSDT", "price": 100.1, "qty": 0.2},
    )
}
```

news：

```python
(
    {"dt": datetime(...), "headline": "...", "symbols": ("BTCUSDT",)},
    {"dt": datetime(...), "headline": "..."},
)
```

输入中的 `date_key` 和 `symbol_key` 在回调中统一为 `dt`、`symbol`。其他字段名保持不变，因此
`price_key="last_price"` 不会把用户字段重命名为 `close`。

回调载荷必须与内核状态隔离。实现可以使用只读映射，也可以为每个 Strategy 提供安全快照；不能让
一个 Strategy 修改载荷后影响 Broker 或其他 Strategy。

## 6. Exchange 公开接口

### 6.1 内存数据入口

```python
exchange.set_bars(
    data,
    *,
    date_key: str = "dt",
    symbol_key: str = "symbol",
    price_key: str | None = "close",
) -> None

exchange.set_books(
    data,
    *,
    date_key: str = "dt",
    symbol_key: str = "symbol",
    price_key: str | None = None,
) -> None

exchange.set_trades(
    data,
    *,
    date_key: str = "dt",
    symbol_key: str = "symbol",
    price_key: str | None = "price",
) -> None

exchange.set_news(
    data,
    *,
    date_key: str = "dt",
    symbol_key: str | None = "symbol",
) -> None
```

支持的数据容器：

- `pandas.DataFrame`；
- `polars.DataFrame`；
- `list[dict]`。

共同规则：

1. `date_key` 必须存在且可以转换为时间。
2. bars、books、trades 的 `symbol_key` 必须存在且为非空字符串。
3. 核心不擅自大写或修改 symbol；来源专用 Feed 可以明确规范化来源 symbol。
4. `price_key` 非 `None` 时，该字段必须存在且值为有限正数。
5. `price_key=None` 表示这个数据源不更新 Broker 参考价格。
6. bars、books 同一来源同一 `(dt, symbol)` 只能有一条。
7. trades 同一来源同一 `(dt, symbol)` 可以有多条，并保持稳定顺序。
8. news 同一 dt 可以有多条，symbol 可缺省；`symbol_key` 存在时才归一化为 `symbol`。
9. 调用同一个 `set_*` 两次时，后一次显式替换对应的内存来源；不会影响 `add_feed` 注册的其他来源。
10. 每个已注册来源必须至少产生一条记录；可选但当前为空的数据类型不需要注册。

`close` 只是 `set_bars` 的 `price_key` 便利默认值，不是 Bar schema 的必需字段。传入
`price_key="last_price"` 后，Exchange 既不校验 `close`，也不会合成 `close`。`open/high/low/volume`
同样都是用户数据字段，不是内核强制 schema。

### 6.2 Feed 与运行入口

```python
exchange.add_feed(feed) -> None
exchange.add_strategy(strategy) -> None
exchange.remove_strategy(strategy_id) -> None

exchange.run() -> None
```

历史回测只保留 `run()`。`set_*` 接收的数据本来就在内存中；`add_feed` 注册的 Feed 逐行读取。
是否使用缓存、数据库分页或文件块是具体 Feed 的实现细节，不应成为 Exchange 的公开模式。

`add_feed` 不允许静默覆盖同名 Feed，本次也不增加使用率不明的 `replace_feed`。需要替换自定义来源时，
在 `run()` 前构建正确的 Exchange。

## 7. `price_key` 与参考价格设计

### 7.1 `price_key` 的唯一职责

`price_key` 是来源的字段配置：

```text
当前记录[price_key]
  -> 校验为有限正数
  -> 写入当前时间点的 prices[symbol]
```

`price_key` 不表示：

- 这个价格一定是收盘价；
- Strategy 必须按这个字段读取信号；
- 数据记录必须包含 `close`。

`price_key` 是当前记录的顶层 key，不支持点路径或 callable。如果价格需要由 bid/ask 计算，Feed 或用户表格
先生成 `mid` 字段，再设置 `price_key="mid"`。Exchange 只需要知道字段名，不需要为它建立事件、候选价或
解析器对象。

### 7.2 各数据类型的取价规则

|数据类型|取价规则|
|---|---|
|bars|取每个 symbol 当前记录的 `price_key`|
|books|只有显式设置 `price_key` 时取值，例如预计算的 `mid`|
|trades|取每个 symbol 当前时间点最后一笔 Trade 的 `price_key`|
|news|不接受 `price_key`，永远不更新价格|

“最后一笔 Trade”按来源内稳定顺序定义，不按 Python 容器偶然顺序定义。

### 7.3 一个 symbol 只有一个价格来源

一次 `run()` 中，某个 symbol 第一次出现价格时，当前 Feed 就成为它的价格来源。后续任何时间点收到
另一个启用 `price_key` 的 Feed 时，Exchange 在更新 Broker 前立即报错，即使两个数值恰好相同也不例外。
这不需要另一个“价格解析”配置：

```python
# bars 负责交易价格，trades 只作为策略输入
exchange.set_bars(bars, price_key="last_price")
exchange.set_trades(trades, price_key=None)
```

不允许 Feed 注册顺序、回调顺序或“后来者覆盖”决定价格。这条约束虽然严格，但它使
`price_key` 本身就足以表达价格所有权，避免增加 `price_source`。

参考价属于一次 Exchange 回测的市场假设，不是每个 Broker 各自的字段选择。如果需要对同一 symbol 比较两种
价格定义，应运行两个独立回测，不在同一 Exchange 中让不同 Broker 得到不同的“市场现价”。

### 7.4 缺失价格

Broker 自然保留每个 symbol 最近一次的参考价格，因此稀疏多标数据可以沿用已知价格。不再引入
`price_missing` 模式。

如果 symbol 从未获得过参考价格，而账户又需要用它估值、触发条件或无显式价格下单，必须抛出
带 symbol、dt 和修复建议的错误。未来如果真实用例需要限制价格时效，再独立设计；本次不预留模式开关。

### 7.5 成交价格与参考价格不得互相修改

用户下单接口继续允许：

```python
self.broker.submit_market_order("BTCUSDT", qty=1)
self.broker.submit_market_order("BTCUSDT", qty=1, price=100.5)
```

规则：

1. `price=None` 时使用 Broker 当前参考价格成交。
2. 显式 `price=` 只指定本次成交价格。
3. 显式成交价格不能反向修改 Broker 的参考价格。
4. `price_dt` 只描述显式成交价格的时间，不改变 Exchange 时钟。
5. 限价单和退出条件在当前 mini 模型中使用选定参考价格触发。
6. 显式成交价格可以完成当前订单，但不能替代后续时间点的持仓参考价格。

这样可以避免用户为了模拟滑点传入成交价格时，意外重估整个账户。

### 7.6 当前 Kline 成交假设

本次重构保持 v0 的简化语义：Strategy 回调中的无显式价格市价单，立即按当前参考价格成交。
当 `price_key="close"` 且策略使用当前 close 产生信号时，这等价于 close-on-close 假设，可能对某些策略
过于乐观。README 和示例必须明确这一点，不能把它包装成真实撮合。

下一时间点成交需要独立的订单时序设计，不能通过偷偷改用下一行数据实现；它不属于本次接口重构。

## 8. Feed 高级接口

一个 Feed 只负责一种公开数据类型，并逐行产生历史记录。它采用鸭子类型，用户无需继承或导入
一个 Feed 基类：

```python
class MyFeed:
    name = "my-bars"
    data_type = "bars"
    price_key = "last_price"  # 可选

    def rows(self):
        yield {"dt": ..., "symbol": "BTCUSDT", "last_price": 100.0}
```

Feed 记录使用标准 `dt` 字段；bars、books、trades 使用标准 `symbol` 字段，news 可以没有
symbol。`set_*` 接口仍允许通过 `date_key/symbol_key` 适配用户现有表格，而 Feed 作者在 `rows()`
内完成来源字段归一化。

Feed 可选声明 `price_key`。未声明时按数据类型取默认值：bars 为 `"close"`、trades 为 `"price"`、
books 和 news 为 `None`。自定义字段名的 Feed 显式声明，例如 `price_key = "last_price"`。News Feed
不能声明价格字段。

`rows()` 必须按 `dt` 非递减产生记录，每次调用返回新的可迭代对象。启用 `price_key` 时，每条可定价记录
都必须包含该字段且值为有限正数。文件、网络和数据库资源由生成器自己在 `try/finally` 或上下文
管理器中打开与关闭；Exchange 在正常、异常和提前结束时都关闭支持 `close()` 的迭代器。
这一条约定同时覆盖小数据和大数据，不再需要 `FeedEvent`、`prepare/close`、能力位或回放模式。

一个混合存储文件由多个具名 Feed 读取，每个 Feed 仍只产生一种 `data_type`。不支持
`data_type="custom"` 的通用出口。

## 9. 多来源合并规则

Exchange 在同一 dt 收齐所有来源后按数据类型合并。

### 9.1 bars 和 books

- 不同 Feed 提供不同 symbol：合并为一个完整截面。
- 不同 Feed 提供相同 symbol：抛出带两个 Feed 名的 `ValueError`。
- 不根据 Feed 注册顺序、优先级或价格值决定覆盖关系。

### 9.2 trades

- 同一 Feed 内同一 symbol 可以有多条，保持来源顺序。
- 不同 Feed 同时提供同一 symbol：抛出带两个 Feed 名的 `ValueError`，因为回调负载没有来源维度。
- 不同 Feed 提供不同 symbol：合并。

### 9.3 news

- 多个 Feed 的 News 可以拼接。
- 排序使用 Feed 注册顺序和来源内序号，结果必须确定。
- 如果策略需要新闻来源，来源应作为新闻记录的业务字段提供，不能依赖内部 Feed 名称注入。

### 9.4 Feed 注册顺序

不提供 `feed_priority`。Feed 注册顺序只用于 news 拼接等无冲突场景的确定性排序，不能覆盖重复
Bar/Book、选择 Broker 价格或改变来源内顺序。

## 10. 时间与调度语义

### 10.1 时间规范

1. 所有时间统一为带 UTC 时区的 `datetime.datetime`。
2. 无时区输入按 UTC 解释。
3. 保留 `datetime` 可表达的精度，不主动截断到毫秒。
4. 无效时间、NaT、无限数值和时间回退必须报错。
5. `set_*` 数据由 Exchange 排序；Feed 的 `rows()` 必须按非递减 dt 输出。

### 10.2 单个时间点的执行顺序

```text
读取并收齐所有来源的当前 dt
  -> 校验重复和来源冲突
  -> 按各 Feed 的 price_key 生成唯一的 symbol -> price
  -> 对每个 Portfolio 批量更新全部 Position
  -> 统一检查保证金、强平和市场日切
  -> 处理 pending 限价单
  -> 检查退出条件
  -> on_bars（若有）
  -> on_books（若有）
  -> on_trades（若有）
  -> on_news（若有）
  -> 记录权益和持仓历史
```

关键不变式：

1. Broker 每个 dt 只进行一次市场状态推进。
2. 全仓组合不能按 symbol 逐个检查保证金。
3. 每个 Strategy 每种数据类型每个 dt 最多收到一次回调。
4. Strategy 回调开始时，Broker 已经看到该 dt 的完整参考价格集合。
5. 一个 Broker 被多个 Strategy 共享时，市场状态仍只处理一次。

## 11. 内部架构

内部设计不把每个动词都变成一个类。目标中只新增一个私有记录 `_Feed`，其余是 Exchange 的小方法
和 `run()` 当前时间点的局部变量。

```text
set_* / feed.rows()
          |
          v
      Exchange.run
      - 按 dt 归并各来源
      - 形成 bars/books/trades/news
      - 按 price_key 形成 prices
          |
          +----> broker.update_prices(dt, prices)
          |
          +----> on_bars/on_books/on_trades/on_news
```

### 11.1 唯一私有数据源记录

概念性结构如下，实施时可以是小 dataclass 或具名元组：

```python
@dataclass
class _Feed:
    name: str
    data_type: Literal["bars", "books", "trades", "news"]
    price_key: str | None
    rows: Callable[[], Iterable[Mapping]]
```

`set_*` 先把现有表格归一化并排序，再注册成 `_Feed`；`add_feed` 把 Feed 的 `rows` 直接注册进同一
结构。`callback`、`mode`、能力位和优先级都可以从 `data_type` 推导或根本不需要，不作为状态保存。

### 11.2 单一回放循环

`run()` 为每个 `_Feed` 创建一个迭代器，用小根堆按 dt 归并。对每个 dt 只创建下列普通局部结构：

```python
bars: dict[str, Mapping]
books: dict[str, Mapping]
trades: dict[str, list[Mapping]]
news: list[Mapping]
prices: dict[str, float]
```

主循环可以保持在以下尺度：

```python
for dt, source_rows in self._rows_by_time():
    data, prices = self._collect(dt, source_rows)
    self._update_brokers(dt, prices, data)
    self._dispatch(dt, data)
```

以上不是新的领域类，也不穿过多层接口。收齐当前 dt 后，Exchange 先完成重复检查和价格提取，再一次
更新 Broker，最后分发非空回调。这条循环同时适用于内存表格和大型 Feed，不保留两套调度实现。
回放期间另用一个普通 `price_owner: dict[symbol, feed_name]` 检查某个 symbol 是否换了价格来源。

### 11.3 Broker 边界

Exchange 只用 `dt` 和完整的 `Mapping[str, float]` 更新 Broker。Broker 不接收 `_Feed` 或通用批次对象，
也不知道 `close`、`last_price`、`price_key` 或数据类型。建议内部边界是：

```python
broker.update_prices(dt, prices)
broker.process_pending_orders(dt)
broker.check_exit_rules(dt, data)
```

`update_prices` 必须在组合层面批量更新，不退回 v0 按 symbol 反复推进整个账户的问题。这是内部唯一
需要强制的原子边界，不需要 `TimeBatch` 类才能表达。`data` 只在自定义退出条件中作为不透明
的当前数据上下文转发；Broker 不从它解析参考价格。

### 11.4 明确不引入的概念

本次不引入 `SourceAdapter`、`ReplayCursor`、`TimeBatch`、`BatchItem`、`SliceProjector`、
`PriceCandidate` 和 `PriceResolver`。将来只有当一个概念确实拥有需要跨方法维护的独立状态/不变式，
或已出现多个真实实现，且无法用小方法清晰表达时，才单独提取类。

## 12. Broker 用户接口边界

现有交易接口继续保留：

```python
submit_market_order
submit_limit_order
cancel_order
order_target_size
order_target_value
order_target_percent
close_position
close_portfolio
set_exit
clear_exit
add_exit
```

主路径推荐目标仓位接口：

```python
self.broker.order_target_percent("BTCUSDT", 0.8)
```

用户只有在明确模拟自定义成交价时才传 `price=`：

```python
self.broker.order_target_percent("BTCUSDT", 0.8, price=modeled_fill_price)
```

所有下单类接口继续统一返回 `Order`。合法但无需交易返回 `skipped`，业务拒绝返回 `rejected`，
参数和状态编程错误抛异常。

## 13. 错误语义

本次不新增公开异常类层级，使用 Python 标准异常：

|错误|典型原因|用户动作|
|---|---|---|
|`TypeError`|Feed 或记录的结构不符合接口|修正对象或容器类型|
|`ValueError`|缺字段、无效值、乱序、重复数据、已注册来源为空、价格来源冲突或缺价|根据消息修正具体来源|

错误消息必须包含相关 feed、data_type、symbol、dt 和参数值，不能要求用户通过堆栈猜测来源。
将来只在用户出现稳定的程序化捕获需求时，再引入少量 minbt 异常基类。

数据缺失和来源冲突属于正确性错误，不依赖默认关闭的 logger warning。

## 14. 性能与资源边界

1. `set_*` 表示数据已经在内存中，可以预先归一化和排序。
2. Feed 逐行读取；Exchange 额外内存为 `O(D + K)`，`D` 是当前 dt 的记录数，`K` 是 Feed 数。
3. 多来源归并时间为 `O(E log K)`。
4. 同一 dt 有大量 Trade 时，该时间点本身可能很大，不承诺严格常数内存。
5. 回调载荷隔离不能通过无界深拷贝实现；优先使用不可变记录和只读视图。
6. Feed 迭代器和数据库资源在正常、异常和提前结束路径都必须释放。

## 15. 公开导出

顶层 `minbt` 推荐只导出稳定策略概念：

```text
Exchange
Strategy
Broker
Order
Market
markets
退出条件相关类型和函数
logger
```

不再从顶层导出通用 `Bar`、`News` 事件构造类型。具体 Feed 放在 `minbt.data`；自定义 Feed
按 `name/data_type/rows()` 的鸭子类型契约实现，不要求导入公开 Protocol。不公开 `FeedEvent`、Cursor
或批次类型。

数据包公开命名必须表达真实格式：

```text
BinanceKlineFeed
BinanceKlineCsvFeed
BinanceKlineIosqlFeed
```

不能使用看似通用、实际只读取 Binance Kline 格式的 `CsvBarsFeed` 等名称。

## 16. 当前实现到目标设计的迁移

### 16.1 删除或替换

|当前实现|目标|
|---|---|
|`Strategy.on_bar`|删除|
|公开 `Bar(kind, data)`|移出普通用户接口，内部记录不承诺兼容|
|公开通用 `kind` 路由|替换为 bars/books/trades/news 固定类型|
|`DataFeedProtocol.events() -> MarketEvent`|替换为无需继承的 `rows() -> Mapping` Feed 契约|
|按 Feed 分别调用同一类型回调|合并后每种类型每 dt 调用一次|
|`Broker(mark_price="kind.field")`|删除；数据来源自己的 `price_key` 就是唯一配置|
|Broker 从 `TimeBatch` 再读原始字段|Exchange 按 `price_key` 传入简单 `symbol -> price`|
|`TimeBatch/ReplayCursor/PriceResolver` 类|删除；收敛为 `_Feed` 与单一回放循环|
|`run(load_mode=...)`|删除；历史 Feed 统一按时间逐行产生数据|
|显式订单 price 更新 Broker mark|禁止；仅影响本次成交|
|重叠来源只 warning|数据冲突直接报错|
|顶层导出 `Bar`、`News`|删除通用事件构造类型；具体业务行继续使用 Mapping|

### 16.2 保留

- v0 风格的 `set_bars/set_books/set_trades/set_news`；
- v0 风格的分类 Strategy 回调；
- `self.broker` 作为唯一交易入口；
- 同一 dt 收齐全部来源后再处理的正确性；
- 当前版 Portfolio 批量价格更新能力，但改用简单 `symbol -> price` 边界；
- 大数据 Feed 逐行读取能力；
- 确定性排序、重复校验和资源生命周期；
- 当前 Broker、Order、Portfolio、Market 和退出条件主体接口。

### 16.3 文档迁移

1. README 快速开始只介绍 Kline、`on_bars`、Broker 和结果查询。
2. OrderBook、Trade、News 分别作为进阶但正式支持的章节。
3. `price_key` 在数据接入章节一次解释完整；不出现 `price_source`。
4. 删除回放模式、Cursor、TimeBatch、FeedEvent 和 Feed 能力位文档。
5. 删除所有 `on_bar`、通用 `Bar.kind` 和通用 CSV Bar 信封示例。
6. 明确当前参考价格立即成交的回测假设。

## 17. 验收标准

### 17.1 用户接口

1. 普通 Kline 示例只实现 `on_bars`，不出现 `Bar`、kind、MarketData 或回放模式。
2. `price_key="close"`、`"price"`、`"last_price"` 均可运行并得到一致的账户结果。
3. `price_key=None` 的信号数据可以回调，但不能隐式更新账户价格。
4. 单标的和多标的使用完全相同的 Strategy 结构。
5. OrderBook、Trade、News 示例分别只实现对应具名回调。
6. `Strategy` 不再存在 `on_bar`。

### 17.2 正确性

1. 同一 dt 多 symbol 的全仓估值不依赖 symbol 顺序。
2. 多 Feed 非重叠 symbol 合并为一次完整回调。
3. 多 Feed 重叠数据在 Strategy 回调前失败。
4. 一次 `run()` 中同一 symbol 出现第二个启用 `price_key` 的来源时失败，不静默切换。
5. 显式成交价格不会改变参考价格和其他持仓估值。
6. pending 订单和退出条件每个 dt 只检查一次。
7. 同一 Broker 被多个 Strategy 共享时只推进一次。
8. 空区间、缺 symbol、错误表名和错误文件路径不会产生“成功的空回测”。

### 17.3 回放与资源

1. `set_*` 与产生相同行记录的 Feed 得到相同回调、订单、权益和持仓。
2. 乱序 Feed 在第一条时间回退记录处失败。
3. Feed 正常结束和各类异常路径都释放迭代器及其底层资源。
4. 同一历史 Feed 对两个全新回测都返回独立迭代器并产生相同记录。
5. 公开历史查询返回类型不受可选依赖是否安装影响。

### 17.4 文档

1. 设计索引只有一个当前数据/回调契约入口。
2. README、使用 Skill、示例和签名契约测试与本文一致。
3. 过期文档明确标注被替代，不再让读者自行拼接冲突结论。

## 18. 推荐实施顺序

1. 先冻结 Strategy、Exchange、Broker 的目标签名和 API 契约测试。
2. 用一个 `_Feed` 记录统一 `set_*` 和 `add_feed`，删除通用事件信封与能力位。
3. 将两套回放路径合并为一个按 dt 归并的循环，并用普通局部容器收齐当前时间点。
4. 恢复 `price_key` 提取；Exchange 一次向 Broker 传递 `symbol -> price`。
5. 删除 `on_bar`、公开通用 kind 路由、TimeBatch 链路和顶层 Bar/News 导出。
6. 修正显式订单价格修改参考价格的问题。
7. 迁移 Kline、CSV、iosql、Binance、OrderBook、Trade、News Feed 到逐行协议。
8. 更新示例、README、使用 Skill 和全部设计索引。
9. 补齐顺序无关、来源冲突、价格歧义、空数据和资源异常测试，完整 review 后不保留永久兼容层。

## 19. 最终设计原则

用户看到的是：

```text
数据属于哪一类
  -> 实现对应的 on_bars/on_books/on_trades/on_news
  -> 通过 self.broker 表达交易意图
```

内核处理的是：

```text
按时间归并多个 Feed
  -> 收齐当前 dt 的四类数据
  -> 按 price_key 得到唯一的 symbol -> price
  -> 批量更新账户并确定性分发回调
```

普通 Kline 用户不应为了内部通用性写 `data.bars[...]`，也不应理解 `Bar.kind` 或回放器概念。内部也不应
为每个处理步骤创建一个类。在本设计中，一个 `_Feed`、一个回放循环和一个 Broker 批量价格边界已经足够；
只有真实用例证明它们不足时才增加概念。
