# DESIGN-002 数据源与 on_xx 回调设计稿

## 状态

当前有效设计。

本设计定义 Exchange 的数据接入和策略回调命名。Broker、账户初始状态、多市场规则、目标仓位和函数式止盈止损见 `DESIGN-001-broker-account-market-api.md`。

## 当前实现判断

截至本设计稿编写时，当前代码状态如下：

- 已实现：`Exchange.set_data(data, date_key=...)`。
- 已实现：旧接口 `Strategy.on_data(row)`。
- 已实现：旧接口 `Strategy.on_bar(dt, rows_by_symbol)`。
- 已实现：多标的同一 `dt` 下先整体更新 broker 最新价，再调用 `on_bar`。
- 未实现：推荐新接口 `Strategy.on_bars(dt, bars)`。
- 未实现：推荐新入口 `Exchange.set_bars(...)`。
- 未实现：`on_books/on_trades/on_news`。
- 未实现：多数据源统一调度。

README 和 examples 迁移后，应只展示 `on_bars`，旧的 `on_data/on_bar` 只作为兼容接口。

## 核心目标

minbt 的目标仍然是最简、方便、快捷的回测系统，不做大而全事件系统。

但 Exchange 应该能自然扩展到多类同一时间点数据，例如：

- 多标的 K 线或类 K 线数据。
- 盘口快照。
- 交易明细聚合。
- 新闻。
- 因子。
- 用户自定义同时间切片数据。

因此用户回调不应命名为过泛的 `on_data`，也不应把所有数据都塞进复杂 `on_event`。

推荐统一为同型 `on_xx`：

```python
def on_bars(self, dt, bars):
    ...

def on_books(self, dt, books):
    ...

def on_trades(self, dt, trades):
    ...

def on_news(self, dt, news):
    ...
```

所有 `on_xx` 都遵循同一个规则：

> `on_xx(self, dt, data)` 表示在同一个回测时间 `dt`，收到某一类数据 `xx` 的完整时间切片。

当前 MVP 只实现 `on_bars(dt, bars)`。

## 设计原则

1. 一个数据类型一个回调，不混用。
2. 所有回调都使用统一签名：`on_xx(self, dt, data)`。
3. `dt` 永远表示当前回测时钟。
4. `data` 永远表示当前 `dt` 下该数据类型的完整切片。
5. 当前只实现 bars；未来扩展其他数据类型时新增同型回调，不重写现有语义。
6. 不引入通用 `Event` 对象，避免把最简回测系统做成事件框架。
7. 策略交易仍通过 `self.broker` 完成，不在 Strategy 上增加交易语法糖。
8. 单标的是多标的的特例，不提供单标的专用数据结构。

## 为什么不用 on_tick

`on_tick` 曾经作为候选，但不推荐。

原因：

- `tick` 容易被理解为逐笔 tick 行情。
- 未来有 bars、books、trades、news 时，`on_tick` 无法表达数据类型。
- 如果 `on_tick` 里混入所有数据，会逼近 `on_event`，复杂度上升。
- 用户只做 K 线回测时，`on_bars` 更直接。

## 当前 MVP：bars

### 数据接入

推荐新入口：

```python
exchange.set_bars(data, date_key="dt")
```

兼容旧入口：

```python
exchange.set_data(data, date_key="dt")
```

兼容规则：

- `set_data(...)` 保留为旧接口。
- 在文档里，`set_data(...)` 解释为 bars 数据的兼容入口。
- 初期 `set_bars(...)` 可以直接调用现有 `set_data(...)` 实现。

### bars 输入结构

输入至少需要：

```text
dt
symbol
close
```

可选：

```text
open
high
low
volume
```

示例：

```python
[
    {"dt": "2024-01-01", "symbol": "BTCUSDT", "close": 100.0},
    {"dt": "2024-01-01", "symbol": "ETHUSDT", "close": 50.0},
    {"dt": "2024-01-02", "symbol": "BTCUSDT", "close": 101.0},
    {"dt": "2024-01-02", "symbol": "ETHUSDT", "close": 49.0},
]
```

### bars 回调结构

统一推荐：

```python
class Strategy:
    def on_bars(self, dt, bars):
        pass
```

其中：

```python
bars: dict[str, bar]
```

`bars` 永远是 `{symbol: bar}`。

单标的也是同一结构：

```python
def on_bars(self, dt, bars):
    bar = bars["BTCUSDT"]
    price = bar["close"]
    self.broker.submit_market_order("BTCUSDT", qty=1, price=price)
```

多标的：

```python
def on_bars(self, dt, bars):
    for symbol, bar in bars.items():
        price = bar["close"]
        self.broker.order_target_percent(symbol, 0.25, price=price)
```

### 命名理由

选择 `on_bars(dt, bars)`：

- `bars` 明确表示 K 线或类似 bar 结构。
- `bars` 可以容纳 OHLCV、日线、分钟线、因子 bar、用户自定义 bar。
- 复数表示同一 `dt` 下多个 symbol 的截面。
- 单标的是多标的特例，也仍然是 `bars`。
- `rows` 是表格实现细节，不应进入用户接口。

## 未来扩展：books

### 为什么叫 on_books

推荐：

```python
def on_books(self, dt, books):
    ...
```

不推荐：

```python
def on_orderbooks(self, dt, orderbooks):
    ...
```

理由：

- `on_orderbooks` 太长。
- `orderbook` 绑定具体盘口形态。
- `books` 可以覆盖 orderbook、Level 1、Level 2、聚合盘口、自定义盘口结构。
- 抽象层级与 `bars` 一致。

### books 数据接入

未来推荐：

```python
exchange.set_books(book_data, date_key="dt")
```

### books 回调

```python
class BookStrategy(Strategy):
    def on_books(self, dt, books):
        book = books["BTCUSDT"]
        best_bid = book["bids"][0][0]
        best_ask = book["asks"][0][0]
```

语义：

- `books` 是 `{symbol: book}`。
- 每次回调是同一 `dt` 的盘口截面。
- 不影响 `on_bars` 的语义。

建议结构：

```python
books = {
    "BTCUSDT": {
        "symbol": "BTCUSDT",
        "bids": [(100.0, 1.2), (99.9, 2.0)],
        "asks": [(100.1, 0.8), (100.2, 1.5)],
    }
}
```

MVP 不实现 books 撮合。

## 未来扩展：trades

交易明细可能同一 `dt` 下一个 symbol 有多条 trade，因此 payload 可以是 list：

```python
exchange.set_trades(trade_data, date_key="dt")
```

回调：

```python
class TradeStrategy(Strategy):
    def on_trades(self, dt, trades):
        btc_trades = trades["BTCUSDT"]
        volume = sum(trade["qty"] for trade in btc_trades)
```

语义：

```python
trades: dict[str, list[trade]]
```

建议结构：

```python
trades = {
    "BTCUSDT": [
        {"price": 100.0, "qty": 0.1, "side": "buy"},
        {"price": 100.1, "qty": 0.2, "side": "sell"},
    ]
}
```

注意：这里的 `qty` 表示交易明细里的成交数量，属于交易动作或成交记录，不是持仓状态。

## 未来扩展：news

新闻不一定按 symbol 严格对应，也可以按主题或全局列表组织。

推荐先用全局列表：

```python
exchange.set_news(news_data, date_key="dt")
```

回调：

```python
class NewsStrategy(Strategy):
    def on_news(self, dt, news):
        for item in news:
            if "BTCUSDT" in item["symbols"]:
                ...
```

语义：

```python
news: list[news_item]
```

建议结构：

```python
news = [
    {
        "title": "...",
        "symbols": ["BTCUSDT"],
        "sentiment": 0.4,
    },
]
```

这说明 `on_xx` 的第二个参数不强制必须是 `{symbol: item}`；它由数据类型决定。但每个 `on_xx` 内部必须稳定。

## 多数据源调度规则

MVP 不实现多数据源调度。只实现 bars。

未来同时存在 bars、books、trades、news 时，Exchange 按时间推进：

1. 收集所有数据源当前最小 `dt`。
2. 对每个数据源取该 `dt` 的数据切片。
3. 更新 broker 最新价所需的数据源。
4. broker 检查 pending order、保证金、退出规则。
5. 按固定顺序调用对应回调。
6. 记录策略权益和持仓历史。

推荐默认顺序：

```text
on_bars
on_books
on_trades
on_news
```

顺序必须固定，不能依赖字典遍历或数据注册顺序。

未来一旦实现多数据源，必须明确：

- 同一 `dt` 下多个回调的顺序。
- 哪些数据源会更新 broker 最新价。
- 缺失某类数据时是否跳过回调。
- 同一 `dt` 下策略多次下单是否允许。
- 同一 `dt` 下退出规则和用户回调谁先执行。

## 与 Broker 的关系

无论数据类型如何，交易入口保持不变：

```python
self.broker.submit_market_order(...)
self.broker.order_target_percent(...)
self.broker.close_position(...)
```

`on_xx` 只负责给策略提供同一时间点的数据切片，不负责交易。

Broker 只应该依赖必要市场价格，不应该理解策略的信号逻辑。

## 与旧接口的关系

当前已有：

- `on_data(row)`：每行 bars 数据调用一次。
- `on_bar(dt, rows_by_symbol)`：每个 bars 时间截面调用一次。

问题：

- 它们都是 bars 数据入口，却一个行级、一个截面级。
- 用户需要判断该用哪一个。
- 多标的策略容易误用 `on_data`。
- 文档需要反复解释单标的和多标的差异。

新设计：

```python
def on_bars(self, dt, bars):
    ...
```

兼容策略：

1. 新增 `Strategy.on_bars(dt, bars)`。
2. `Exchange.run()` 优先调用 `on_bars`。
3. 如果策略未重写 `on_bars`，再兼容旧 `on_bar`。
4. 如果策略也未重写 `on_bar`，再兼容旧 `on_data`。
5. README 和新示例只展示 `on_bars`。
6. `on_data` 和 `on_bar` 标记为兼容接口，不再作为推荐用户接口。

长期：

- 用户文档只保留 `on_bars`。
- 旧接口保留一段时间，避免破坏已有策略。
- 等版本边界明确后，再考虑删除旧接口。

## Exchange API 建议

### MVP

```python
exchange.set_bars(data, date_key="dt")
exchange.set_data(data, date_key="dt")  # 兼容旧入口，等价于 set_bars
```

### 未来扩展

```python
exchange.set_books(data, date_key="dt")
exchange.set_trades(data, date_key="dt")
exchange.set_news(data, date_key="dt")
```

不建议一开始就做：

```python
exchange.add_feed(name, data, ...)
```

原因：

- 通用 feed API 会迫使用户理解数据源注册、事件类型、调度顺序。
- 这和最简目标冲突。
- 等数据类型真的变多后，再抽象 `add_feed`。

## 单标的示例

```python
class SmaStrategy(Strategy):
    def on_init(self):
        self.symbol = "BTCUSDT"
        self.prices = []

    def on_bars(self, dt, bars):
        bar = bars[self.symbol]
        price = bar["close"]
        self.prices.append(price)
        if len(self.prices) < 30:
            return

        ma10 = sum(self.prices[-10:]) / 10
        ma30 = sum(self.prices[-30:]) / 30
        target = 0.8 if ma10 > ma30 else 0.0
        self.broker.order_target_percent(self.symbol, target, price=price)
```

特点：

- 即使只有一个标的，`bars` 仍然是字典。
- 不提供 `bar = bars.price()` 这类额外封装。
- 用户用 `self.symbol` 减少重复字符串。

## 多标的轮动示例

```python
from collections import defaultdict


class RotationStrategy(Strategy):
    def on_init(self):
        self.history = defaultdict(list)

    def on_bars(self, dt, bars):
        for symbol, bar in bars.items():
            self.history[symbol].append(bar["close"])

        ready = all(len(values) >= 20 for values in self.history.values())
        if not ready:
            return

        momentum = {
            symbol: values[-1] / values[-20] - 1
            for symbol, values in self.history.items()
        }
        selected = sorted(momentum, key=momentum.get, reverse=True)[:2]

        for symbol, bar in bars.items():
            target = 0.45 if symbol in selected else 0.0
            self.broker.order_target_percent(symbol, target, price=bar["close"])
```

特点：

- 轮动策略天然需要同一 `dt` 下所有 symbol 的截面。
- `on_bars` 避免行级 `on_data` 造成时序偏差。

## bars + news 未来组合示例

```python
class NewsAwareStrategy(Strategy):
    def on_init(self):
        self.sentiment = {}

    def on_news(self, dt, news):
        for item in news:
            for symbol in item["symbols"]:
                self.sentiment[symbol] = item["sentiment"]

    def on_bars(self, dt, bars):
        for symbol, bar in bars.items():
            if self.sentiment.get(symbol, 0) > 0.5:
                self.broker.order_target_percent(symbol, 0.5, price=bar["close"])
```

这个示例只说明未来扩展方向，MVP 不实现 `on_news`。

## 明确不做

MVP 不做：

- 通用 `on_event(event)`。
- 通用 `exchange.add_feed(...)`。
- books/orderbook 撮合。
- trade 逐笔撮合。
- 多数据源复杂同步。
- 缺失数据自动补齐。
- Tick 对象包装。
- 单标的专用回调。

这些能力可以后续按实际需要逐步加入。

## 推荐实施顺序

### MVP-1：bars 回调统一

1. 新增 `Strategy.on_bars(dt, bars)`。
2. 新增 `Exchange.set_bars(data, date_key=None)`。
3. `Exchange.set_data(...)` 保持兼容并代理到 bars 语义。
4. `Exchange.run()` 优先调用 `on_bars`。
5. README 和 examples 全部迁移到 `on_bars`。
6. `on_data/on_bar` 标记为兼容接口。

### MVP-2：Broker 便捷交易能力

1. `Broker.order_target_size(...)`。
2. `Broker.order_target_value(...)`。
3. `Broker.order_target_percent(...)`。
4. `Broker(initial_positions=...)`。

### MVP-3：退出规则与市场模型

1. 函数式止盈止损。
2. `SimpleMarket` 扩展点。
3. `ChinaAStockMarket` 和 `CryptoMarket` 最小版本。

### MVP-4：更多数据类型

只有当真实需求出现时，再实现：

1. `on_books`。
2. `on_trades`。
3. `on_news`。

## 结论

`on_xx(dt, data)` 是长期方向：

- 当前 bars 场景清晰：`on_bars(dt, bars)`。
- 未来盘口数据用 `on_books(dt, books)`，不使用过长的 `on_orderbooks`。
- 未来 trades/news 有自然扩展点。
- 不需要引入重型事件系统。
- 单标的、多标的保持一致结构。
- 交易入口仍然是 broker。

这条路线既保留 minbt 的最简目标，也避免后续接入非 bars 数据时命名和结构失控。

