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
- 未实现：T+1、T+0、lot size、tick size、涨跌停等多市场规则扩展。
- 不进入当前 MVP：以已有持仓启动 broker 的账户快照初始化。

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
|可平持仓|`available_size`|当前允许平仓的数量，非负|
|锁定持仓|`locked_size`|当前不可平仓的数量，非负|
|目标市值|`target_value`|希望调到多少名义金额|
|目标权重|`target_percent`|希望调到组合权益的多少比例|

当前 MVP 不提供账户快照初始化，因此用户通常不需要填写持仓状态字段。`size/available_size/locked_size` 主要是 broker 内部状态和查询结果，不作为主路径初始化参数。

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

### 目标仓位计算公式

`order_target_percent` 的计算必须明确：

```python
equity = broker.get_equity(portfolio_id=portfolio_id)
target_value = equity * target_percent
target_size = target_value / price
delta_qty = target_size - broker.get_position_size(symbol, portfolio_id=portfolio_id)
```

然后执行：

```python
broker.submit_market_order(symbol, qty=delta_qty, price=price, portfolio_id=portfolio_id)
```

语义：

- `target_percent > 0` 表示目标多头名义金额。
- `target_percent < 0` 表示目标空头名义金额，是否允许由 `MarketModel` 判断。
- `price` 显式传入时使用该价格；未传入时使用 broker 最新价。
- 如果没有可用价格，返回失败并记录日志。
- 手续费、lot size、tick size、是否允许做空、T+1 等约束由 `MarketModel` 和 `Portfolio` 校验。
- 目标仓位接口不保证一定成交；它只是把用户目标转换为订单意图。

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
- `close_position` 默认是全平语义，不能全平时返回失败，不应静默部分平仓。
- 如果市场规则不允许全部平仓，例如 A 股 T+1，当 `available_size < abs(size)` 时返回失败。
- 如果用户明确只想平掉可用部分，应使用显式接口，例如未来的 `close_available_position(...)` 或 `close_position(..., allow_partial=True)`。

这个约束是为了避免用户以为已经清仓，实际还残留被 T+1 锁定的仓位。

## 初始账户状态

### MVP 决策

当前 MVP 只支持从现金开始：

```python
broker = Broker(
    initial_cash=100_000,
    fee_rate=0.001,
)
```

语义：

- `initial_cash` 是初始现金。
- 回测开始时没有初始持仓。
- 用户不需要理解账户快照、初始持仓成本、初始保证金、持仓批次等概念。
- 策略重心放在信号和交易决策上。

不在 `Broker.__init__` 中提供：

```python
Broker(initial_positions=...)
```

原因：

- 大多数回测从现金开始，少数“接真实账户状态继续回测”的场景不应污染主接口。
- 初始持仓会引入成本价、杠杆、保证金、可用数量、锁定数量、持仓批次等复杂字段。
- 当前内部 `Position` 使用保证金模型，现货初始持仓和杠杆初始持仓的权益语义容易混淆。
- 用户目标是快速验证策略，不是还原完整真实账户。

如果将来确实需要从真实账户继续回测，应单独设计显式快照入口，例如：

```python
broker = Broker.from_snapshot(snapshot)
```

或：

```python
broker.load_snapshot(snapshot)
```

该能力进入后续版本，不进入当前 MVP，也不作为 `Broker(...)` 构造参数。

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

`available_size` 和 `locked_size` 永远是非负数。

当 `size > 0` 时，`available_size` 表示当前可卖出平多的数量。

当 `size < 0` 时，`available_size` 表示当前可买入平空的数量。

示例：A 股当天买入 100 股：

```python
position.size = 100
position.available_size = 0
position.locked_size = 100
```

下一个交易日：

```python
position.size = 100
position.available_size = 100
position.locked_size = 0
```

这些字段由 broker 和 `MarketModel` 在交易后维护，不需要用户在初始化时填写。

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

重要约束：

- 第一阶段一个 `Broker` 绑定一个 `MarketModel`。
- 如果用户需要同时交易多个市场，第一阶段建议使用多个 broker 或多个 portfolio 外部组合。
- 未来如果确有必要，再支持 `market_by_symbol` 或 symbol 路由，不在当前 MVP 引入。

### MarketModel 是特征组合，不是硬编码市场分支

`ChinaAStockMarket` 和 `CryptoMarket` 不应该是写满特殊分支的独立 broker。它们只是市场特征的预设组合。

市场至少由这些特征定义：

```python
class MarketModel:
    trading_calendar: TradingCalendar
    settlement: SettlementRule
    lot_size: LotSizeRule
    tick_size: TickSizeRule
    fee_model: FeeModel
    allow_short: bool
    price_limit: PriceLimitRule | None
```

其中：

- `trading_calendar` 定义可交易日期、可交易时间、如何从 `dt` 得到交易日。
- `settlement` 定义 T+0、T+1、卖出资金是否立即可用等规则。
- `lot_size` 定义最小交易手数或最小交易数量。
- `tick_size` 定义价格最小变动单位。
- `fee_model` 定义佣金、印花税、最低费用等。
- `allow_short` 定义是否允许净空头。
- `price_limit` 定义涨跌停等价格限制。

这样 A 股和加密资产只是不同配置：

```python
ChinaAStockMarket = MarketModel(
    trading_calendar=ChinaAStockCalendar(),
    settlement=TPlusOneSettlement(),
    lot_size=FixedLotSize(100),
    tick_size=FixedTickSize(0.01),
    allow_short=False,
    price_limit=DailyPriceLimit(...),
)

CryptoMarket = MarketModel(
    trading_calendar=AlwaysOpenCalendar(),
    settlement=TPlusZeroSettlement(),
    lot_size=SymbolLotSize(...),
    tick_size=SymbolTickSize(...),
    allow_short=True,
    price_limit=None,
)
```

这比在 broker 内部写 `if market == "cn_stock"` 更可维护。

### MarketModel 职责

`MarketModel` 是内部接口，不是用户主接口。它负责：

- 校验订单是否允许提交。
- 规范化订单数量和价格。
- 计算成交价、手续费、税费。
- 处理 T+1 锁定与解锁。
- 处理 lot size、tick size、涨跌停。
- 判断限价单是否成交。
- 判断当前 `dt` 是否在可交易时间内。
- 判断当前 `dt` 属于哪个交易日。
- 判断某个持仓批次是否已经可卖或可平。

MVP 内部契约可以从最小开始：

```python
class MarketModel:
    def is_trading_time(self, dt):
        return True

    def trading_day(self, dt):
        return dt.date()

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
- 始终可交易，除非用户数据本身没有该时间点。
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
- 7x24 小时可交易。
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

不同加密 symbol 的最小交易数量、最小名义金额、tick size 可能不同。MVP 可以先支持统一配置，后续再支持：

```python
CryptoMarket(
    min_qty={"BTCUSDT": 0.0001, "ETHUSDT": 0.001},
    min_notional={"BTCUSDT": 5, "ETHUSDT": 5},
    tick_size={"BTCUSDT": 0.01, "ETHUSDT": 0.01},
)
```

或者支持 callable：

```python
CryptoMarket(
    min_qty=lambda symbol: metadata[symbol]["min_qty"],
)
```

这个能力可以后期追加，不应阻塞当前 broker 主接口。

### ChinaAStockMarket

A 股市场至少需要：

- T+1。
- 交易日历和交易时段。
- 买入数量通常必须是 100 股整数倍。
- 卖出订单数量不得超过当前可用持仓。
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

T+1 不应只靠静态 `locked_size` 判断。更完整的内部状态应记录持仓批次：

```python
PositionLot(
    size=100,
    cost_price=1700,
    opened_trading_day="2024-01-02",
)
```

在卖出或平仓时，`ChinaAStockMarket` 用当前 `dt` 计算当前交易日：

```python
current_day = market.trading_day(dt)
```

然后判断：

```python
lot.opened_trading_day < current_day
```

只有已经跨过交易日的买入批次才进入 `available_size`。如果当天买入后同一天触发 `close_position`，默认应该返回失败。

MVP 可以先用聚合的 `available_size/locked_size` 实现；但设计上必须保留按交易日批次演进的空间。

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
    if atr is None:
        return False
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

### add_exit_rule 签名

推荐唯一签名：

```python
broker.add_exit_rule(
    symbol,
    rule=None,
    *,
    name=None,
    condition=None,
    state=None,
    portfolio_id="default",
)
```

语义：

- `rule` 是 `ExitRule` 对象，可选。
- `condition` 是函数，签名为 `condition(ctx) -> bool`。
- `name` 是规则名称，用于日志和调试。
- `state` 是可选状态，可以是 dict，也可以是无参函数，触发检查时求值。
- `portfolio_id` 指定规则作用于哪个 portfolio。
- `rule` 和 `condition` 至少提供一个。
- 如果同时提供 `rule` 和 `condition`，应抛出参数错误，避免语义重复。

因此下面两种写法都允许：

```python
self.broker.add_exit_rule("BTCUSDT", stop_loss_pct(0.03))
```

```python
self.broker.add_exit_rule(
    "BTCUSDT",
    name="atr_stop",
    condition=atr_stop,
    state=lambda: {"atr": self.atr},
)
```

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

需要明确：

- 退出规则使用当前 bar 的价格和上一轮策略已经写入的状态。
- 如果某个指标只能在当前 `on_bars` 中计算，那么它默认会在下一根 bar 的退出检查中生效。
- 如果用户必须基于当前 bar 先更新指标再退出，应在 `on_bars` 中手写退出逻辑。
- bar 级回测无法知道同一根 bar 内高低价路径。MVP 中退出规则按当前 `close` 或用户指定价格字段判断，不模拟 intrabar 顺序。

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
- 不在可交易时间。
- 数量不满足 lot size。
- 价格不满足 tick size。
- 达到涨跌停。
- 没有可用价格。

严重状态错误才抛异常，例如：

- 初始化参数不合法。
- 内部持仓状态不一致，例如 `available_size + locked_size != abs(size)`。
- 数据缺少必要字段。

后续可以引入 `OrderResult`，但 MVP 保持 bool 也可以接受。

## 典型场景示例

### 场景 1：加密资产趋势策略，从现金开始

```python
broker = Broker(
    initial_cash=100_000,
    fee_rate=0.001,
    market=CryptoMarket(),
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

这是 minbt 的主路径：从现金开始，用策略决定何时建仓、调仓和平仓。

### 场景 2：A 股 T+1，当日买入后不能同日清仓

```python
broker = Broker(
    initial_cash=100_000,
    fee_rate=0.0003,
    market=ChinaAStockMarket(),
)
```

```python
class AShareStopStrategy(Strategy):
    def on_init(self):
        self.symbol = "600519.SH"
        self.entry_price = None

    def on_bars(self, dt, bars):
        price = bars[self.symbol]["close"]

        if self.entry_price is None and self.entry_signal(price):
            ok = self.broker.submit_market_order(self.symbol, qty=100, price=price)
            if ok:
                self.entry_price = price

        if self.entry_price is not None and price < self.entry_price * 0.97:
            ok = self.broker.close_position(self.symbol, price=price)
            if ok:
                self.entry_price = None
```

如果买入和平仓发生在同一交易日，`ChinaAStockMarket` 根据 `trading_day(dt)` 和 T+1 规则拒绝 `close_position`。`close_position` 默认表达全平意图，不能全平时返回失败，不静默部分平。

### 场景 3：函数式 ATR 止损

```python
def atr_stop(ctx):
    atr = ctx.state["atr"]
    if atr is None:
        return False
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
        # 本 bar 更新出的 atr 会在下一次 broker 退出检查中使用。
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

本节是 Broker 子系统内部顺序。全局实施顺序以 `docs/design/README.md` 为准；从用户接口一致性看，应先完成 `on_bars` 回调统一，再实现 Broker 增强能力。

### Broker-1：目标仓位与持仓可用性

1. 支持 `order_target_size`。
2. 支持 `order_target_value`。
3. 支持 `order_target_percent`。
4. 支持 `Position.available_size/locked_size` 作为内部状态。

### Broker-2：MarketModel 扩展点

1. 抽出默认 `SimpleMarket`，保持当前行为。
2. 所有订单执行经过 `MarketModel`。
3. 支持可交易时间检查。
4. 支持交易日计算。
5. 支持 `available_size/locked_size` 的市场规则校验。
6. 增加 `ChinaAStockMarket` 和 `CryptoMarket` 的最小版本。

### Broker-3：函数式退出规则

1. 支持 `broker.add_exit_rule(...)`。
2. 支持 `broker.clear_exit_rules(...)`。
3. 支持 `stop_loss_pct(...)`。
4. 支持 `take_profit_pct(...)`。
5. 在 `Exchange.run()` 中接入退出规则检查顺序。

### Broker-4：最小限价单

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
Broker(..., market=ChinaAStockMarket())
```

这条路线同时满足：

- 最简回测系统目标。
- 从现金开始快速验证策略。
- 函数式止盈止损。
- A 股 T+1 与加密 T+0 的扩展。
- 后续限价单能力。
