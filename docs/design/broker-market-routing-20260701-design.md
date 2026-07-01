# Strategy-Broker 与多市场路由设计

日期：2026-07-01

状态：设计稿

## 背景

minbt 的目标是最简、方便、快捷的回测系统，不是完整交易所模拟器。

当前稳定用户模型是：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001)
strategy = MyStrategy(strategy_id="demo", broker=broker)

exchange = Exchange()
exchange.set_bars(data)
exchange.add_strategy(strategy)
exchange.run()
```

策略内部直接调用 broker：

```python
class MyStrategy(Strategy):
    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["close"]
        self.broker.order_target_percent("BTCUSDT", 0.8, price=price)
```

本设计稿回答三个问题：

1. `Strategy` 是否应该持有 `broker`。
2. 一个策略多个 broker 是否应该成为主路径。
3. 跨市场策略应该如何表达市场规则。

## 结论

推荐模型：

```text
一个 Strategy
一个 Broker
多个 Portfolio
多个 Market
symbol -> Market
portfolio + symbol -> Position
统一 Orders
```

用户主路径保留：

```python
strategy = MyStrategy(strategy_id="demo", broker=broker)
```

多市场通过 `Broker` 内部路由解决：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001, market=markets.CRYPTO)

broker.add_portfolio("ashare", cash=60_000)
broker.add_portfolio("crypto", cash=40_000)

broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH", "510300.SH"])
```

策略仍然只通过 `self.broker` 交易：

```python
self.broker.order_target_percent("600519.SH", 0.5, price=a_price, portfolio="ashare")
self.broker.order_target_percent("BTCUSDT", 0.5, price=btc_price, portfolio="crypto")
```

## 设计原则

### 1. Strategy 运行时应该有 broker

策略的真实场景是：

```text
读取当前时间截面数据 -> 判断交易条件 -> 调用 broker 下单
```

所以 `self.broker` 是合理的用户接口。

不推荐改成：

```python
def on_bars(self, dt, bars, broker):
    ...
```

原因：

- 每个回调都增加参数。
- `on_bars/on_books/on_trades/on_news` 全部膨胀。
- broker 来源仍然需要解释。
- 不如 `self.broker` 贴近真实策略写法。

### 2. Strategy 构造时传 broker 可以保留

主路径继续推荐：

```python
strategy = MyStrategy(strategy_id="demo", broker=broker)
```

原因：

- 用户能明确看到策略依赖哪个 broker。
- 策略内部 `self.broker` 的来源清楚。
- 没有隐藏注入。
- 不需要额外理解 Exchange 运行时装配。

不推荐把主路径改成：

```python
exchange = Exchange(broker=broker)
strategy = MyStrategy(strategy_id="demo")
exchange.add_strategy(strategy)
```

这个写法的问题是：用户会疑惑 `self.broker` 是什么时候、从哪里来的。

可以未来支持高级装配：

```python
exchange.add_strategy(strategy, broker=broker)
```

但不作为当前主路径。

### 3. 一个策略多个 broker 不进入主路径

暂不推荐：

```python
self.brokers["binance"].order_target_percent(...)
self.brokers["okx"].order_target_percent(...)
```

原因：

- 增加用户接口复杂度。
- `get_total_equity()` 语义变复杂。
- 历史权益记录变复杂。
- 止盈止损属于哪个 broker 需要额外规则。
- order id 是否全局唯一需要额外规则。
- portfolio 和 broker 的边界容易混淆。
- 同一 symbol 在多个 broker 的价格来源需要额外建模。

当前阶段更适合用：

```text
一个 broker + 多 portfolio + 多 market routing
```

这已经能覆盖大多数回测需求：

- 跨市场轮动。
- A 股 + 加密资产组合。
- 跨品种套利信号。
- 不同资金池独立管理。
- 不同 symbol 使用不同交易规则。

### 4. Exchange 不表达真实交易所

当前 `Exchange` 更准确的角色是：

```text
回测时钟 + 数据调度器
```

它负责：

- 接收历史数据。
- 按时间推进。
- 聚合同一时间截面。
- 更新 broker 最新价。
- 触发策略回调。

它不负责：

- 判断是否 T+1。
- 判断是否允许做空。
- 判断最小交易手。
- 判断交易时间。
- 维护资金、订单、持仓。

因此多市场规则不应该放进 `Exchange`。

## 当前代码状态

当前代码已经具备：

|能力|当前状态|
|---|---|
|多 portfolio|已支持|
|统一订单记录|已支持|
|按 portfolio + symbol 查询持仓|已支持|
|单一 broker 级 market|已支持|
|symbol -> market 路由|未支持|

当前核心限制是：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001, market=markets.A_STOCK)
```

此时 broker 里的所有 symbol 都会使用 A 股规则。

如果同时交易：

```text
600519.SH
BTCUSDT
```

那么 `BTCUSDT` 也会被当成 A 股：

- 不允许做空。
- T+1。
- 100 股一手。
- 受 A 股交易时间限制。

反过来，如果 broker 使用 crypto market：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001, market=markets.CRYPTO)
```

那么 A 股 symbol 也会被当成 crypto：

- T+0。
- 可以做空。
- 可以小数数量。
- 没有 A 股交易时间限制。

这就是当前需要补齐的设计缺口。

## 目标用户接口

### Broker 构造

```python
broker = Broker(
    initial_cash=100_000,
    fee_rate=0.001,
    market=markets.CRYPTO,
)
```

语义：

- `market` 是默认市场规则。
- 未被显式映射的 symbol 使用默认市场规则。
- `market=None` 时默认使用 `Market(name="Default")`。

### 添加市场路由

```python
broker.add_market(
    name: str,
    market: Market,
    symbols: list[str],
) -> None
```

示例：

```python
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH", "510300.SH"])
```

语义：

- 注册一个命名市场规则。
- 将 `symbols` 映射到该市场规则。
- 后续这些 symbol 下单、调仓、平仓、限价单成交、退出条件触发时，都使用该市场规则。
- `add_market(...)` 是配置期接口，应在回测运行和任何交易发生前调用。
- market 应在 broker 内部复制，避免用户修改预设对象影响已有 broker。
- `name` 是 broker 内部路由名；broker 内部复制 market 后，将复制对象的 `name` 设为该路由名。
- 如果任一 symbol 已出现在当前持仓、订单、pending order 或 `last_prices` 中，调用应抛错，避免历史状态按旧规则、未来状态按新规则。

### 查询 symbol 市场

```python
broker.get_market(symbol: str) -> Market
```

语义：

- 返回该 symbol 当前使用的 Market。
- 如果 symbol 未显式映射，返回默认 Market。
- 返回值是当前 Market 配置快照，用于查看和调试。
- 返回值不保证对象身份，不应用 `is` 判断是否为 broker 内部对象。
- 用户修改返回对象不会影响 broker 内部规则。

该接口主要用于调试和测试，不是策略主路径必需概念。

### 推荐示例：纯 crypto

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001, market=markets.CRYPTO)

strategy = CryptoStrategy(strategy_id="crypto", broker=broker)
```

### 推荐示例：纯 A 股

```python
broker = Broker(initial_cash=100_000, fee_rate=0.0003, market=markets.A_STOCK)

strategy = AStockStrategy(strategy_id="ashare", broker=broker)
```

### 推荐示例：跨市场

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001, market=markets.CRYPTO)

broker.add_portfolio("ashare", cash=60_000)
broker.add_portfolio("crypto", cash=40_000)

broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH", "510300.SH"])

strategy = CrossMarketStrategy(strategy_id="cross_market", broker=broker)
```

策略：

```python
class CrossMarketStrategy(Strategy):
    def on_bars(self, dt, bars):
        a_price = bars["600519.SH"]["close"]
        btc_price = bars["BTCUSDT"]["close"]

        if self.should_buy_a_stock(bars):
            self.broker.order_target_percent(
                "600519.SH",
                0.8,
                price=a_price,
                portfolio="ashare",
            )

        if self.should_buy_crypto(bars):
            self.broker.order_target_percent(
                "BTCUSDT",
                0.8,
                price=btc_price,
                portfolio="crypto",
            )
```

## 命名选择

### 推荐：add_market

```python
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])
```

优点：

- 简短。
- 和 `add_portfolio` 风格一致。
- 表达“给 broker 增加一组市场规则”。
- 适合初始化阶段一次性声明。

### 不推荐：register_market

```python
broker.register_market(...)
```

问题：

- 更长。
- 更偏内部框架语义。
- 对用户不比 `add_market` 更清楚。

### 不推荐：set_market

```python
broker.set_market("600519.SH", markets.A_STOCK)
```

问题：

- 更像运行中修改状态。
- 容易引出是否允许覆盖、是否影响已有持仓、是否影响 pending order 的问题。
- 不如初始化阶段显式添加一组 symbols 简单。

### 不推荐：add_market_rules

```python
broker.add_market_rules(...)
```

问题：

- 更啰嗦。
- 当前对象已经叫 `Market`，不需要再引入 `Rules` 概念。

最终推荐：

```python
broker.add_market(name, market, symbols)
```

## 行为定义

### 默认市场

每个 broker 必须有一个默认 market。

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001, market=markets.CRYPTO)
```

未显式映射 symbol 时：

```python
broker.get_market("BTCUSDT").name == "Crypto"
```

如果默认 market 是 `Market(name="Default")`，则返回快照的 `name` 是 `"Default"`。

### symbol 唯一归属

一个 symbol 同一时间只能属于一个 market。

以下行为应抛错：

```python
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])
broker.add_market("Other", markets.CRYPTO, symbols=["600519.SH"])
```

原因：

- 避免同一 symbol 使用多个交易规则。
- 避免用户误把 symbol 写进多个市场。
- 保持接口简单。

如果未来确实需要重分配 symbol，再单独设计显式接口，不在当前阶段加入。

### add_market 调用时机

`add_market(...)` 只能在配置期调用。

以下情况应抛错：

- symbol 已有当前持仓。
- symbol 已出现在历史订单中。
- symbol 有 pending order。
- symbol 已有 broker 最新价记录。

原因：

- 已有持仓可能存在 T+1 锁仓批次。
- pending order 的提交校验和未来成交校验必须使用同一市场规则。
- 历史订单、退出条件和当前持仓生命周期必须保持同一规则来源。
- `last_prices` 表示 broker 已经进入过该 symbol 的运行状态，运行中改市场会造成不可调试的隐式行为变化。

### name 唯一

market name 必须唯一。

```python
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])
broker.add_market("AStock", markets.A_STOCK, symbols=["510300.SH"])  # 抛错
```

原因：

- 避免同名市场规则被静默覆盖。
- 保持初始化配置可读。

`name` 是 broker 的路由名，不要求和传入的 `market.name` 一致。broker 内部会复制 market，并把复制对象的 `name` 设置为路由名。

示例：

```python
custom = Market(name="CustomA", allow_short=False, t_plus=1)
broker.add_market("AStock", custom, symbols=["600519.SH"])
assert broker.get_market("600519.SH").name == "AStock"
```

### symbols 不能为空

```python
broker.add_market("AStock", markets.A_STOCK, symbols=[])  # 抛错
```

原因：

- 空 market 没有用户价值。
- 避免出现“注册了市场但没有生效”的误解。

### portfolio 与 market 独立

`portfolio` 是资金和持仓隔离。

`market` 是交易规则。

二者不要混用。

第一阶段的 `market routing` 只路由 `Market` 特征：

- 是否允许做空。
- T+0/T+1。
- 最小交易数量。
- 最小名义金额。
- 最小交易手。
- 价格 tick。
- 交易时间。

第一阶段不路由：

- 不同 symbol 的手续费率。
- 不同 market 的默认杠杆。
- 不同 market 的保证金模式。
- 不同 market 的强平模型。

这些仍然由现有 broker 公共参数和下单参数决定：`fee_rate/margin_mode` 在当前用户接口下是 broker 级配置，`leverage` 可以在下单时覆盖。若后续需要按 market 配置手续费或保证金，应单独设计，不混入本次 `add_market(...)`。

允许同一个 portfolio 交易多个 market：

```python
self.broker.order_target_percent("600519.SH", 0.4, price=a_price)
self.broker.order_target_percent("BTCUSDT", 0.4, price=btc_price)
```

如果用户希望资金池隔离，再使用 portfolio：

```python
self.broker.order_target_percent("600519.SH", 0.8, price=a_price, portfolio="ashare")
self.broker.order_target_percent("BTCUSDT", 0.8, price=btc_price, portfolio="crypto")
```

### 同一 symbol 多交易场所

当前阶段不引入 venue 概念。

如果用户要表达 Binance 和 OKX 的同名交易对，应使用不同 symbol：

```text
BTCUSDT.BINANCE
BTCUSDT.OKX
```

或：

```text
BINANCE:BTCUSDT
OKX:BTCUSDT
```

minbt 不在当前阶段定义 symbol 命名规范，只要求 symbol 字符串在用户数据和 broker 中一致。

## 内部接口设计

### Broker 内部状态

推荐结构：

```python
class Broker:
    def __init__(..., market: Market | None = None):
        self._default_market = copy.copy(market) if market is not None else Market(name="Default")
        self._markets = {}
        self._symbol_market_names = {}
```

说明：

- `_default_market` 是默认规则。
- `_markets` 保存通过 `add_market(...)` 注册的命名市场。
- `_symbol_market_names` 保存 `symbol -> market name`。
- 不再把 `self.market` 作为唯一市场规则使用。
- 默认 market 不放进 `_markets`，避免和用户注册的 market name 混淆。

### Broker 市场解析

```python
def _market_for(self, symbol: str) -> Market:
    name = self._symbol_market_names.get(symbol)
    if name is None:
        return self._default_market
    return self._markets[name]
```

对外查询：

```python
def get_market(self, symbol: str) -> Market:
    return copy.copy(self._market_for(symbol))
```

公开查询返回浅拷贝，避免用户通过返回对象隐式修改 broker 内部规则。内部撮合和校验只使用 `_market_for(symbol)`。

`add_market(...)` 内部应复制并重命名 market：

```python
def add_market(self, name: str, market: Market, symbols: list[str]) -> None:
    copied = copy.copy(market)
    copied.name = name
    self._markets[name] = copied
    ...
```

### 需要改用 symbol market 的路径

所有订单相关规则都必须通过 `symbol` 找 market：

```python
market = self._market_for(symbol)
```

包括：

- 市价单校验。
- 限价单提交校验。
- pending limit order 成交校验。
- 目标仓位数量标准化。
- `close_position`。
- `close_portfolio`。
- 退出条件触发后的平仓。
- 成交后的 T+1 锁仓。

### on_new_dt

当前单 market 模型下，`on_new_price(symbol, price, dt)` 发现新 dt 时调用：

```python
self.market.on_new_dt(self, dt)
```

多 market 后不能只调用当前 symbol 对应 market，否则同一 dt 下第一个价格如果来自 crypto，A 股持仓可能不会及时解锁。

推荐改成 broker 统一处理新 dt：

```python
def _on_new_dt(self, dt):
    for market_name, market in self._markets.items():
        symbols = self._symbols_for_market(market_name)
        market.on_new_dt(self, dt, symbols=symbols)

    default_symbols = self._default_market_symbols_from_positions()
    self._default_market.on_new_dt(self, dt, symbols=default_symbols)
```

`Market.on_new_dt` 内部只处理传入 symbols 对应的 positions。

### Market.on_new_dt 签名

推荐内部签名：

```python
def on_new_dt(self, broker, dt, symbols: list[str] | None = None) -> None:
    ...
```

语义：

- `symbols=None` 表示兼容处理 broker 内所有 positions。
- `symbols=[...]` 表示只处理这些 symbol。

因为这是内部接口，允许比用户接口更贴近系统实现。

### default market symbols

默认 market 的 symbol 集合不能只来自显式配置，因为默认 market 的 symbol 是未注册的。

推荐从当前持仓和订单中推导：

```text
所有 broker 已知 symbol - 显式映射 symbol
```

broker 已知 symbol 可以来自：

- 当前 positions。
- pending orders。
- last_prices。
- historical orders。

实现时至少应覆盖 positions 和 pending orders。

## 与当前代码的差异

|位置|当前|目标|
|---|---|---|
|Broker market 状态|`self.market` 单实例|`_default_market + _markets + symbol routing`|
|下单校验|所有 symbol 走同一 market|按 symbol 找 market|
|目标仓位数量标准化|所有 symbol 走同一 market|按 symbol 找 market|
|T+1 解锁|单 market 处理所有 positions|每个 market 只处理自己的 symbols|
|跨市场策略|需要牺牲其中一个市场规则|一个 broker 内同时支持 Market 交易规则差异|
|费率/杠杆/保证金|broker/portfolio/order 级|本设计不改变|

## 不进入当前设计

### 不做一个策略多个 broker

不作为主路径。

未来如果确实需要，可以单独设计高级对象：

```python
class BrokerGroup:
    ...
```

但当前阶段不引入。

### 不做真实交易所 venue 模型

不设计：

- exchange id。
- venue id。
- broker venue adapter。
- 订单簿撮合。
- 队列位置。
- 部分成交路径。
- 交易所级延迟。

### 不做每次下单传 market

不推荐：

```python
self.broker.order_target_percent("600519.SH", 0.8, price=price, market="AStock")
```

原因：

- 啰嗦。
- 容易传错。
- 与 symbol 天然归属市场的心智模型不一致。

### 不做市场子类

继续使用特征配置：

```python
Market(
    name="AStock",
    allow_short=False,
    t_plus=1,
    lot_size=100,
    tick_size=0.01,
    require_dt=True,
    weekdays_only=True,
    trading_sessions=(("09:30", "11:30"), ("13:00", "15:00")),
)
```

不引入：

```python
class ChinaAStockMarket(Market):
    ...
```

原因：

- 不必要。
- 增加实体。
- 不如特征配置直接。

## 后续实现顺序

推荐按以下顺序实施：

1. 在 `Broker` 增加 `_default_market`、`_markets`、`_symbol_market_names`。
2. 增加 `broker.add_market(...)` 和 `broker.get_market(symbol)`。
3. 在 `add_market(...)` 中校验配置期边界：symbol 不能已出现在 positions、orders、pending orders 或 `last_prices`。
4. 增加 `_market_for(symbol)` 内部方法。
5. 把订单校验、数量标准化、成交后处理全部改成 `_market_for(symbol)`。
6. 修改 T+1 解锁逻辑，确保每个 market 只处理自己的 symbols。
7. 添加跨市场测试：
   - A 股 symbol 必须 100 股一手。
   - crypto symbol 可以小数下单。
   - A 股 T+1 不能当天卖。
   - crypto T+0 可以当天卖。
   - 同一个 broker 内两者同时成立。
   - 运行期对已知 symbol 调用 `add_market(...)` 应抛错。
   - `get_market(symbol)` 返回快照，修改返回对象不影响 broker 内部规则。
8. 添加跨市场示例。
9. 更新 README 和主系统设计文档。

## 设计验收标准

### 用户接口

用户应该能用以下代码表达跨市场回测：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001, market=markets.CRYPTO)
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])

strategy = MyStrategy(strategy_id="cross", broker=broker)
```

策略代码不需要知道 market routing：

```python
self.broker.order_target_percent("600519.SH", 0.5, price=a_price)
self.broker.order_target_percent("BTCUSDT", 0.5, price=btc_price)
```

### 行为

同一个 broker 内：

- `600519.SH` 使用 A 股规则。
- `BTCUSDT` 使用默认 crypto 规则。
- 两者共享 broker 的订单系统。
- 两者可以用 portfolio 做资金隔离。
- 两者第一阶段不支持按 market 使用不同手续费率或保证金模式。
- 退出条件仍绑定 order。
- `get_total_equity()` 返回所有 portfolio 的总权益。

### 复杂度

不新增：

- 多 broker 主路径。
- broker group。
- venue。
- 每次下单 market 参数。
- 市场子类。

## 最终推荐

当前阶段应该保留：

```python
strategy = MyStrategy(strategy_id="demo", broker=broker)
```

不要改成 Exchange 注入 broker。

跨市场能力应通过：

```python
broker.add_market(name, market, symbols)
```

实现。

这条路径最符合 minbt 当前目标：

- 策略写法不变。
- 用户概念少。
- 支持常见跨市场交易规则差异。
- 不引入多 broker 复杂度。
- 不把 Exchange 做成真实交易所。
