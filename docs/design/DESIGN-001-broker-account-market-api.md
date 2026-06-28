# DESIGN-001 Broker、账户初始状态、多市场与退出规则设计稿

## 状态

当前有效设计。

本设计替代旧稿 `DESIGN-001-user-order-exit-api.md` 的全部内容。旧稿中的 `on_tick` 回调、`on_orderbooks` 命名和部分过期示例不再作为实施依据。

配套设计：

- `DESIGN-002-data-feeds-and-callbacks.md`：数据接入与 `on_bars/on_books/on_trades/on_news` 回调设计。

## 当前实现判断

截至本设计稿编写时，当前代码状态如下：

- 已实现：`Broker.submit_market_order(...)`。
- 已实现：基础现金、持仓、保证金、逐仓/全仓的组合账户逻辑。
- 已实现：`Position.size`、`Position.cost_price`、`Position.margin`、`Position.unrealized_pnl` 等内部状态。
- 未实现：`Broker.submit_limit_order(...)`，当前直接抛 `NotImplementedError`。
- 未实现：内置止盈止损。示例里的止损是策略手写逻辑，不是 broker 能力。
- 未实现：函数式退出规则。
- 未实现：`order_target_size/value/percent` 目标仓位接口。
- 未实现：以已有持仓启动 broker 的账户快照初始化。
- 未实现：T+1、T+0、lot size、tick size、涨跌停等多市场规则扩展。

README 如果提到“支持限价单”“支持止盈止损”，必须继续标记为未完成，直到代码真正实现。

## 核心目标

minbt 的目标是最简、方便、快捷的回测系统，不是完整交易所模拟器。

核心用户心智模型应该保持为：

```python
class MyStrategy(Strategy):
    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["close"]
        self.broker.submit_market_order("BTCUSDT", qty=1, price=price)
```

策略负责判断“现在想做什么交易”，broker 负责判断“这笔交易能否执行、如何影响账户”。

不要把交易接口堆到 `Strategy` 上，例如不推荐：

```python
self.long(...)
self.short(...)
self.rebalance(...)
```

这些会把一个最简回测系统变成难以维护的 DSL。用户应该始终清楚：交易发生在 broker 上。

## 用户接口与内部接口分层

用户接口应该表达真实意图，尽量短：

```python
self.broker.submit_market_order("BTCUSDT", qty=1, price=price)
self.broker.order_target_percent("BTCUSDT", target_percent=0.8, price=price)
self.broker.add_exit_rule("BTCUSDT", stop_loss_pct(0.03))
```

内部接口应该表达系统约束，允许更精确：

```python
MarketModel.validate_order(ctx, order)
MarketModel.fill_market_order(ctx, order)
Portfolio.apply_fill(fill)
Position.lock_size(...)
```

二者不应混用：

- 用户不应该理解 pending order 状态机、T+1 锁定批次、成交模型细节。
- 内部不应该为了表面简洁省略状态边界、错误语义和可测试契约。

## 命名约定

必须统一区分“交易动作”和“账户状态”：

|概念|推荐命名|说明|
|---|---|---|
|订单增量|`qty`|这次买入或卖出多少，可正可负|
|当前持仓|`size`|账户里当前持有多少，可正可负|
|目标持仓|`target_size`|希望调到多少持仓|
|可平持仓|`available_size`|当前允许卖出或平仓的数量，非负|
|锁定持仓|`locked_size`|当前不可卖出或不可平仓的数量，非负|
|目标市值|`target_value`|希望调到多少名义金额|
|目标权重|`target_percent`|希望调到组合权益的多少比例|

`qty` 不应用于账户快照，因为快照不是一笔订单。

推荐：

```python
initial_positions={
    "BTCUSDT": {
        "size": 0.5,
        "cost_price": 60000,
    }
}
```

不推荐：

```python
initial_positions={
    "BTCUSDT": {
        "qty": 0.5,
        "cost_price": 60000,
    }
}
```

## Broker 用户接口

### 基础市价单

继续保留当前最明确的接口：

```python
self.broker.submit_market_order(
    symbol="BTCUSDT",
    qty=1,
    price=price,
)
```

语义：

- `qty > 0` 表示买入或增加多头。
- `qty < 0` 表示卖出或增加空头。
- `qty == 0` 无效。
- `price=None` 时使用 broker 内部最新价。
- 显式传 `price` 时，broker 可以先更新该 symbol 最新价，再执行订单。

### 目标仓位接口

目标仓位接口不是无意义语法糖，而是快捷回测的高频真实需求。用户经常关心“调到多少”，而不是“这次增量应该是多少”。

推荐新增：

```python
self.broker.order_target_size("BTCUSDT", target_size=1.5, price=price)
self.broker.order_target_value("BTCUSDT", target_value=20_000, price=price)
self.broker.order_target_percent("BTCUSDT", target_percent=0.5, price=price)
```

语义：

- `order_target_size`：把持仓数量调到目标数量。
- `order_target_value`：把名义金额调到目标金额，正数做多，负数做空。
- `order_target_percent`：把名义金额调到当前 portfolio 权益的目标比例。

这些接口内部最终仍然转化为 `submit_market_order(symbol, qty=delta, price=price)`。

示例：

```python
current_size = broker.get_position_size("BTCUSDT")
target_size = 2.0
delta_qty = target_size - current_size
broker.submit_market_order("BTCUSDT", qty=delta_qty, price=price)
```

用户不需要每次手写这段，因此提供 `order_target_size`。

### 清仓接口

推荐保留在 broker 上：

```python
self.broker.close_position("BTCUSDT", price=price)
```

清仓语义：

- 对多头提交负数量订单。
- 对空头提交正数量订单。
- 如果持仓为空，返回失败并记录日志，不应抛出难以恢复的异常。
- 如果市场规则不允许全部平仓，例如 A 股 T+1，只能按 `available_size` 执行或明确拒绝。

## 初始账户状态

### 为什么需要

真实使用中，用户经常不是从全现金开始，而是已经持有资产：

- 当前账户有 20,000 USDT 和 0.5 BTC。
- 当前 A 股账户有 50,000 现金和 200 股贵州茅台。
- 当前基金组合已有多个 ETF，要从今天开始做再平衡。

如果通过第一根 bar 下单伪造初始持仓，会产生错误：

- 产生不存在的成交记录。
- 扣除不存在的手续费。
- 成本价变成回测第一根价格。
- 初始现金和真实账户不一致。
- T+1 可卖数量无法表达。

因此 broker 必须支持账户快照初始化。

### 推荐用户接口

```python
broker = Broker(
    initial_cash=20_000,
    fee_rate=0.001,
    initial_positions={
        "BTCUSDT": {
            "size": 0.5,
            "cost_price": 60_000,
        },
        "ETHUSDT": {
            "size": 2.0,
            "cost_price": 3_000,
        },
    },
)
```

语义：

- `initial_cash` 是初始可用现金。
- `initial_positions` 是回测开始前已经存在的持仓。
- 初始化持仓不是订单，不产生手续费、成交记录或交易日志。
- 初始持仓成本由 `cost_price` 决定。
- 初始权益会随第一根行情更新而反映浮动盈亏。

### 初始持仓字段

MVP 必须支持：

```python
{
    "size": 0.5,
    "cost_price": 60000,
}
```

建议支持：

```python
{
    "size": 100,
    "cost_price": 1700,
    "available_size": 100,
}
```

或者：

```python
{
    "size": 100,
    "cost_price": 1700,
    "locked_size": 0,
}
```

`available_size` 和 `locked_size` 不能同时传，避免用户传出不一致状态。

如果都不传：

- 默认市场和加密市场：`available_size = abs(size)`。
- A 股市场：初始持仓默认视为已交收，`available_size = abs(size)`。
- 如果用户要模拟“今天刚买入还不能卖”，需要显式传 `locked_size` 或 `available_size`。

### 可用与锁定语义

推荐在 `Position` 里同时表达：

```python
position.size
position.available_size
position.locked_size
```

约束：

```python
available_size + locked_size == abs(size)
```

示例：A 股已有 200 股，其中 100 股可卖：

```python
{
    "size": 200,
    "cost_price": 1700,
    "available_size": 100,
}
```

内部等价于：

```python
locked_size = 100
```

示例：加密资产 T+0：

```python
{
    "size": 0.5,
    "cost_price": 60000,
}
```

内部默认：

```python
available_size = 0.5
locked_size = 0
```

### 多 portfolio 初始化

MVP 可以先只支持默认 portfolio：

```python
Broker(
    initial_cash=100_000,
    initial_positions={
        "BTCUSDT": {"size": 0.5, "cost_price": 60_000},
    },
)
```

如果要支持多 portfolio，不建议把 `portfolio_id` 塞进每个 position 字段。更清楚的接口是：

```python
Broker(
    initial_cash=100_000,
    portfolios={
        "main": {
            "cash": 60_000,
            "positions": {
                "BTCUSDT": {"size": 0.5, "cost_price": 60_000},
            },
        },
        "hedge": {
            "cash": 30_000,
            "positions": {
                "ETHUSDT": {"size": -1.0, "cost_price": 3_000},
            },
        },
    },
)
```

但这不应进入第一阶段。当前项目已有 `add_sub_portfolio`，初始账户能力应先服务默认 portfolio，避免接口膨胀。

## 多市场扩展

### 为什么不能只加参数

市场差异不只是 T+0/T+1：

- 是否允许当日卖出。
- 是否允许做空。
- 最小交易单位。
- 最小下单金额。
- tick size 价格精度。
- 手续费、印花税、最低佣金。
- 涨跌停。
- 限价单成交规则。
- 市价单成交规则。
- 卖出后现金是否马上可用。
- 持仓里哪些数量可卖。

如果在 `Broker` 里加很多参数：

```python
Broker(t_plus=1, lot_size=100, allow_short=False, ...)
```

短期看简单，长期会变成难以维护的参数组合。

如果做多个 broker 子类：

```python
ChinaAStockBroker(...)
CryptoBroker(...)
```

会导致公共逻辑重复，并且策略同时交易多个市场时很难组合。

### 推荐方案：Broker + MarketModel

推荐：

```python
broker = Broker(
    initial_cash=100_000,
    fee_rate=0.001,
    market=SimpleMarket(),
)
```

A 股：

```python
broker = Broker(
    initial_cash=100_000,
    fee_rate=0.0003,
    market=ChinaAStockMarket(),
)
```

加密资产：

```python
broker = Broker(
    initial_cash=100_000,
    fee_rate=0.001,
    market=CryptoMarket(),
)
```

用户策略代码不变：

```python
self.broker.submit_market_order("600519.SH", qty=100, price=price)
```

broker 内部调用 `MarketModel` 处理市场约束。

### MarketModel 职责

`MarketModel` 是内部接口，不是用户主接口。它负责：

- 校验订单是否允许提交。
- 规范化订单数量和价格。
- 计算成交价、手续费、税费。
- 处理 T+1 锁定与解锁。
- 处理 lot size、tick size、涨跌停。
- 判断限价单是否成交。

MVP 内部契约可以从最小开始：

```python
class MarketModel:
    def validate_order(self, ctx, order):
        pass

    def fill_market_order(self, ctx, order):
        return fill

    def on_new_dt(self, ctx, dt):
        pass
```

未来扩展限价单时再增加：

```python
def fill_limit_order(self, ctx, order, bar):
    return fill_or_none
```

不要一开始设计完整交易所撮合协议。

### SimpleMarket

默认市场应保持当前行为：

- T+0。
- 全部持仓都可立即平仓。
- 允许小数数量。
- 不强制 lot size。
- 不强制 tick size。
- 不处理涨跌停。
- 市价单按传入 price 或 broker 最新价成交。

这保证现有用户代码不需要改变。

### CryptoMarket

加密资产市场可以在 `SimpleMarket` 基础上增强：

- T+0。
- 通常允许小数数量。
- 可配置最小数量。
- 可配置最小名义金额。
- 可配置 tick size。
- 可选择是否允许做空。

示例：

```python
CryptoMarket(
    min_qty=0.0001,
    min_notional=5,
    tick_size=0.01,
    allow_short=True,
)
```

### ChinaAStockMarket

A 股市场至少需要：

- T+1。
- 买入数量通常必须是 100 股整数倍。
- 卖出可以按持仓可用数量处理。
- 不允许普通股票做空。
- 支持印花税和佣金模型。
- 支持涨跌停校验。
- 当日买入数量进入 `locked_size`。
- 下一个交易日由 `on_new_dt` 解锁。

示例：

```python
ChinaAStockMarket(
    lot_size=100,
    allow_short=False,
    t_plus=1,
)
```

T+1 示例：

```python
# 第一天买入 100 股
position.size = 100
position.available_size = 0
position.locked_size = 100

# 第二个交易日
position.size = 100
position.available_size = 100
position.locked_size = 0
```

## 函数式止盈止损

### 核心判断

止盈止损不应该以固定字段作为核心抽象：

```python
tp_price=...
sl_price=...
```

固定价格、固定百分比只是特殊情况。真实策略里常见的是：

- ATR 止损。
- 移动止损。
- 最高价回撤止盈。
- 因子失效退出。
- 时间止损。
- 波动率切换退出。

因此核心能力应该是函数式退出规则。

### 推荐用户接口

```python
def atr_stop(ctx):
    atr = ctx.state["atr"]
    return ctx.position.size > 0 and ctx.price < ctx.position.cost_price - 2 * atr


self.broker.add_exit_rule(
    "BTCUSDT",
    name="atr_stop",
    condition=atr_stop,
)
```

当条件触发时，broker 生成一个平仓意图：

```python
broker.close_position(symbol, price=ctx.price)
```

这笔平仓是否能够执行，再交给 `MarketModel` 判断。

### 常规止盈止损 helper

常规百分比止损：

```python
self.broker.add_exit_rule("BTCUSDT", stop_loss_pct(0.03))
```

常规百分比止盈：

```python
self.broker.add_exit_rule("BTCUSDT", take_profit_pct(0.08))
```

它们只是返回规则对象或函数：

```python
def stop_loss_pct(pct):
    def condition(ctx):
        if ctx.position.size > 0:
            return ctx.price <= ctx.position.cost_price * (1 - pct)
        if ctx.position.size < 0:
            return ctx.price >= ctx.position.cost_price * (1 + pct)
        return False
    return ExitRule(name=f"stop_loss_{pct}", condition=condition)
```

### ExitContext

退出规则函数需要一个清晰上下文：

```python
class ExitContext:
    symbol: str
    dt: object
    price: float
    position: Position
    broker: Broker
    portfolio_id: str
    data: object
    state: dict
```

字段说明：

- `symbol`：当前检查的标的。
- `dt`：当前回测时间。
- `price`：当前用于触发判断的价格。
- `position`：当前持仓。
- `broker`：当前 broker，只读使用为主。
- `portfolio_id`：所属 portfolio。
- `data`：当前 bars/books/trades/news 的切片，可选。
- `state`：策略或用户注入的辅助状态，可选。

MVP 可以先少给字段，但必须保证后续兼容增加字段。

### 触发顺序

推荐在每个 `on_bars` 之前检查退出规则：

1. Exchange 推进到当前 `dt`。
2. Broker 更新所有 symbol 最新价。
3. Broker 检查退出规则。
4. 触发的退出规则生成平仓订单。
5. MarketModel 判断平仓是否允许。
6. Strategy 执行 `on_bars(dt, bars)`。

理由：

- 止损不应滞后一根 bar 才执行。
- 策略回调看到的是退出规则处理后的账户状态。
- 用户仍然可以在策略里手写更复杂的退出逻辑。

需要明确：bar 级回测无法知道同一根 bar 内高低价路径。MVP 中退出规则按当前 `close` 或用户指定价格字段判断，不模拟 intrabar 顺序。

### 与多市场的关系

止盈止损负责产生“退出意图”，市场规则负责判断“能否执行”。

例如 A 股当天买入后触发止损：

```python
self.broker.add_exit_rule("600519.SH", stop_loss_pct(0.03))
```

如果 `available_size == 0`：

- 规则可以触发。
- broker 尝试平仓。
- `ChinaAStockMarket` 拒绝订单或只允许平掉可用数量。
- 日志必须记录触发和拒绝原因。

不要让止损规则自己理解 T+1。

## 限价单设计

### 当前优先级

限价单暂不作为第一优先级。

原因：

- 真正的限价单需要 pending order。
- 需要订单取消。
- 需要 bar 内成交路径假设。
- 需要 high/low 字段。
- 可能涉及部分成交。
- 同一根 bar 内止盈和止损先后顺序无法精确知道。

对于 minbt，函数式止盈止损和目标仓位接口更能提升快捷回测体验。

### 最小限价单接口

未来可以支持：

```python
order_id = self.broker.submit_limit_order(
    "BTCUSDT",
    qty=1,
    price=95,
)

self.broker.cancel_order(order_id)
```

MVP 限价单规则：

- 买入限价单：如果 bar 有 `low` 且 `low <= limit_price`，则成交。
- 卖出限价单：如果 bar 有 `high` 且 `high >= limit_price`，则成交。
- 成交价按 limit price。
- 一次性全部成交。
- 不做部分成交。
- 没有 high/low 时不支持限价单，明确报错。
- 不模拟同一 bar 内价格路径。

限价单成交仍应经过 `MarketModel`。

## 执行顺序

bars MVP 推荐顺序：

```text
Exchange 当前 dt
-> 更新 broker 最新价格
-> broker 检查保证金和强平
-> broker 检查函数式退出规则
-> Strategy.on_bars(dt, bars)
-> 记录权益和持仓历史
```

如果未来支持 pending limit orders：

```text
Exchange 当前 dt
-> 更新 broker 最新价格
-> broker 撮合 pending limit orders
-> broker 检查保证金和强平
-> broker 检查函数式退出规则
-> Strategy.on_bars(dt, bars)
-> 记录权益和持仓历史
```

具体顺序必须写进测试，不能只依赖实现细节。

## 错误语义

用户下单失败时，不建议默认抛异常中断整个回测。更适合：

```python
ok = broker.submit_market_order(...)
```

失败返回 `False`，同时记录日志，原因包括：

- 现金不足。
- 持仓不足。
- T+1 不可卖。
- 数量不满足 lot size。
- 价格不满足 tick size。
- 达到涨跌停。
- 没有可用价格。

严重状态错误才抛异常，例如：

- 初始化参数不合法。
- 初始持仓字段矛盾。
- `available_size + locked_size != abs(size)`。
- 数据缺少必要字段。

后续可以引入 `OrderResult`，但 MVP 保持 bool 也可以接受。

## 典型场景示例

### 场景 1：从已有加密账户继续回测

```python
broker = Broker(
    initial_cash=20_000,
    fee_rate=0.001,
    market=CryptoMarket(),
    initial_positions={
        "BTCUSDT": {"size": 0.5, "cost_price": 60_000},
    },
)


class BtcTrend(Strategy):
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

用户不需要伪造第一笔买入。

### 场景 2：A 股已有持仓，T+1 可用数量

```python
broker = Broker(
    initial_cash=50_000,
    fee_rate=0.0003,
    market=ChinaAStockMarket(),
    initial_positions={
        "600519.SH": {
            "size": 200,
            "cost_price": 1700,
            "available_size": 100,
        },
    },
)
```

含义：

- 总持仓 200 股。
- 当前可卖 100 股。
- 另外 100 股被锁定，不能当日卖出。

策略仍然只调用：

```python
self.broker.close_position("600519.SH", price=price)
```

broker 和 market 决定是否全平、部分平或拒绝。

### 场景 3：函数式 ATR 止损

```python
def atr_stop(ctx):
    atr = ctx.state["atr"]
    if ctx.position.size > 0:
        return ctx.price < ctx.position.cost_price - 2.5 * atr
    if ctx.position.size < 0:
        return ctx.price > ctx.position.cost_price + 2.5 * atr
    return False


class AtrStrategy(Strategy):
    def on_init(self):
        self.symbol = "BTCUSDT"
        self.atr = None
        self.broker.add_exit_rule(
            self.symbol,
            name="atr_stop",
            condition=atr_stop,
            state=lambda: {"atr": self.atr},
        )

    def on_bars(self, dt, bars):
        bar = bars[self.symbol]
        self.atr = self.update_atr(bar)
        self.broker.order_target_percent(self.symbol, 0.8, price=bar["close"])
```

### 场景 4：手写退出仍然允许

```python
class ManualExit(Strategy):
    def on_init(self):
        self.symbol = "BTCUSDT"
        self.entry_price = None

    def on_bars(self, dt, bars):
        price = bars[self.symbol]["close"]
        if self.entry_price is None and self.entry_signal(price):
            ok = self.broker.submit_market_order(self.symbol, qty=1, price=price)
            if ok:
                self.entry_price = price

        if self.entry_price is not None and price < self.entry_price * 0.97:
            if self.broker.close_position(self.symbol, price=price):
                self.entry_price = None
```

函数式退出规则是推荐复用能力，不是强制路径。

## 明确不做

第一阶段不做：

- 完整交易所撮合引擎。
- 逐笔订单簿撮合。
- 部分成交。
- 复杂订单状态机。
- 同一根 bar 内高低价路径推断。
- 多市场混合账户自动路由。
- 组合保证金产品。
- 借贷利息、资金费率。
- 企业行为、分红、拆股。

这些都可能重要，但不属于最简快捷回测的第一目标。

## 推荐实施顺序

### MVP-1：账户快照与目标仓位

1. 支持 `Broker(initial_positions=...)`。
2. 支持 `Position.available_size/locked_size`。
3. 支持 `order_target_size`。
4. 支持 `order_target_value`。
5. 支持 `order_target_percent`。

### MVP-2：函数式退出规则

1. 支持 `broker.add_exit_rule(...)`。
2. 支持 `broker.clear_exit_rules(...)`。
3. 支持 `stop_loss_pct(...)`。
4. 支持 `take_profit_pct(...)`。
5. 在 `Exchange.run()` 中接入退出规则检查顺序。

### MVP-3：MarketModel 扩展点

1. 抽出默认 `SimpleMarket`，保持当前行为。
2. 所有订单执行经过 `MarketModel`。
3. 支持 `available_size/locked_size` 的市场规则校验。
4. 增加 `ChinaAStockMarket` 和 `CryptoMarket` 的最小版本。

### MVP-4：最小限价单

1. 支持 pending limit order。
2. 支持 `cancel_order(order_id)`。
3. 基于 bar 的 high/low 判断成交。
4. 不做部分成交和 intrabar 路径模拟。

## 最终结论

推荐架构：

```text
Strategy
-> Broker 用户接口
-> Portfolio / Position 账户状态
-> MarketModel 市场规则
```

用户代码保持简单：

```python
self.broker.order_target_percent("BTCUSDT", 0.8, price=price)
```

内部能力保持可扩展：

```python
Broker(..., initial_positions=..., market=ChinaAStockMarket())
```

这条路线同时满足：

- 最简回测系统目标。
- 从真实账户状态继续决策。
- 函数式止盈止损。
- A 股 T+1 与加密 T+0 的扩展。
- 后续限价单能力。

