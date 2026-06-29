# DESIGN-001 Broker、分仓、市场特征与退出规则设计稿

## 状态

当前有效设计。

本设计替代旧稿中的 `MarketModel/SimpleMarket/ChinaAStockMarket/CryptoMarket` 用户主接口。旧名字保留为兼容入口，但不作为推荐用户接口。

配套设计：

- `DESIGN-002-data-feeds-and-callbacks.md`：数据接入与 `on_bars/on_books/on_trades/on_news` 回调设计。

## 当前实现判断

已实现：

- `Broker.submit_market_order(...)` 市价成交。
- `Broker.order_target_size/value/percent(...)` 目标仓位接口。
- `Broker.add_portfolio(name, cash)` 分仓接口。
- `portfolio="xxx"` 作为下单、查询、退出规则的推荐组合参数。
- `Market(...)` 市场特征配置对象。
- `markets.DEFAULT`、`markets.CRYPTO`、`markets.A_STOCK` 市场预设。
- A 股最小规则：交易时间、交易日、100 股一手、价格 tick、不可做空、T+1 持仓锁定。
- `Position.available_size/locked_size` 内部状态。
- 函数式退出规则、`stop_loss_pct(...)` 和 `take_profit_pct(...)`。
- 旧接口 `portfolio_id`、`add_sub_portfolio`、`MarketModel/SimpleMarket/CryptoMarket/ChinaAStockMarket` 的基础兼容。

未实现：

- `Broker.submit_limit_order(...)`，当前直接抛 `NotImplementedError`。
- pending order 状态机、撮合队列、订单取消。
- 挂单式止损、追踪止损和复杂订单状态管理。
- 涨跌停、每个 symbol 独立最小交易单元等更细市场规则。
- 以已有持仓启动 broker 的账户快照初始化。

README 必须区分两类能力：函数式退出规则已实现；限价单、挂单式止损和追踪止损未实现。

## 核心目标

minbt 的目标是最简、方便、快捷的回测系统，不是完整交易所模拟器。

核心用户心智模型：

```python
class MyStrategy(Strategy):
    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["close"]
        self.broker.submit_market_order("BTCUSDT", qty=1, price=price)
```

策略负责判断“现在想做什么交易”，broker 负责判断“这笔交易能否执行、如何影响账户”。

不推荐把交易接口堆到 `Strategy` 上：

```python
self.long(...)
self.short(...)
self.rebalance(...)
```

这会把最简回测系统变成 DSL。用户应该始终清楚：交易发生在 broker 上。

## 用户接口与内部接口分层

用户接口应该表达真实意图，尽量短：

```python
self.broker.submit_market_order("BTCUSDT", qty=1, price=price)
self.broker.order_target_percent("BTCUSDT", target_percent=0.8, price=price)
self.broker.add_exit_rule("BTCUSDT", stop_loss_pct(0.03))
self.broker.add_portfolio("trend", cash=30_000)
```

内部接口应该表达系统约束，允许更精确：

```python
Market.validate_order(...)
Portfolio.submit_order(...)
Position.lock_size(...)
```

二者不应混用：

- 用户不应该理解 pending order 状态机、T+1 锁定批次、成交模型细节。
- 内部不应该为了表面简洁省略状态边界、错误语义和可测试契约。

## 命名约定

|概念|推荐命名|说明|
|---|---|---|
|订单增量|`qty`|这次买入或卖出多少，可正可负|
|当前持仓|`size`|账户里当前持有多少，可正可负|
|目标持仓|`target_size`|希望调到多少持仓|
|可平持仓|`available_size`|当前允许平仓的数量，非负|
|锁定持仓|`locked_size`|当前不可平仓的数量，非负|
|目标市值|`target_value`|希望调到多少名义金额|
|目标权重|`target_percent`|希望调到组合权益的多少比例|
|组合名称|`portfolio`|用户接口参数，指定在哪个组合交易|
|组合内部标识|`portfolio_id`|兼容和内部接口参数，不推荐新代码使用|

当前 MVP 不提供账户快照初始化，因此用户通常不需要填写持仓状态字段。`size/available_size/locked_size` 主要是 broker 内部状态和查询结果，不作为主路径初始化参数。

## Broker 用户接口

### 创建 Broker

推荐：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001)
```

语义：

- `initial_cash` 代表 broker 初始现金。
- 默认创建 `main` portfolio。
- 默认全部现金进入 `main`。
- 默认不需要 `portfolio_cash`。
- 默认不需要 `portfolio_id`。

`portfolio_cash` 和 `portfolio_id` 仅保留兼容旧代码，不作为推荐用户接口。

### 基础市价单

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
- 显式传 `price` 时，broker 会先更新该 symbol 最新价，再执行订单。

### 目标仓位接口

目标仓位接口不是无意义语法糖，而是快捷回测的高频真实需求。用户经常关心“调到多少”，而不是“这次增量应该是多少”。

```python
self.broker.order_target_size("BTCUSDT", target_size=2, price=price)
self.broker.order_target_value("BTCUSDT", target_value=5_000, price=price)
self.broker.order_target_percent("BTCUSDT", target_percent=0.8, price=price)
```

目标接口仍然经过 broker 和 market 校验：

- 资金不足会失败。
- 不允许做空的市场会拒绝净空头。
- T+1 市场会检查 `available_size`。
- A 股预设会把目标买入数量按整手向 0 方向规范化。

### 分仓接口

推荐：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001)
broker.add_portfolio("trend", cash=60_000)
broker.add_portfolio("mean_reversion", cash=20_000)
```

语义：

- 默认组合名是 `main`。
- `add_portfolio(name, cash)` 从 `main` 的可用现金划拨资金创建新组合。
- 分仓只是资金和持仓隔离，不是独立 broker。
- 所有 portfolio 共享同一个 broker 的 market、fee、杠杆配置。

指定组合交易：

```python
self.broker.order_target_percent("BTCUSDT", 0.8, price=price, portfolio="trend")
self.broker.submit_market_order("ETHUSDT", qty=1, price=price, portfolio="mean_reversion")
```

查询：

```python
broker.get_equity()                    # main
broker.get_equity(portfolio="trend")   # trend
broker.get_cash(portfolio="trend")
broker.get_position_size("BTCUSDT", portfolio="trend")
broker.get_total_equity()              # 所有 portfolio 加未分配兼容现金
```

旧接口：

```python
broker.add_sub_portfolio("old", initial_cash=10_000)
broker.submit_market_order("BTCUSDT", qty=1, portfolio_id="old")
```

旧接口只为兼容存在。新代码不推荐使用，因为它暴露了 `remaining_free_cash` 和内部 ID 命名。

### 关闭组合

```python
broker.close_portfolio("trend")
```

语义：

- 先逐个仓位检查 market 规则。
- 可以全部平仓时才真正执行。
- 任一仓位因 T+1、无价格或市场规则无法平仓，则整个关闭失败。
- 非 `main` 组合关闭后，现金返回 `main`。
- 关闭 `main` 时，现金进入兼容用的未分配现金。

## 市场特征模型

### 推荐用户接口

默认市场：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001)
```

使用预设：

```python
from minbt import Broker, markets

crypto = Broker(initial_cash=100_000, fee_rate=0.0005, market=markets.CRYPTO)
a_stock = Broker(initial_cash=100_000, fee_rate=0.0003, market=markets.A_STOCK)
```

自定义市场特征：

```python
from minbt import Market

a_stock_like = Market(
    name="AStock",
    allow_short=False,
    t_plus=1,
    lot_size=100,
    tick_size=0.01,
    require_dt=True,
    weekdays_only=True,
    trading_sessions=(("09:30", "11:30"), ("13:00", "15:00")),
    allow_daily_bar=True,
)
```

### 为什么不用 ChinaAStockMarket 类

A 股和加密资产不是两套 broker，也不应该要求用户继承市场类。

更简单稳定的模型是：市场是一组特征。

```python
Market(name="AStock", t_plus=1, lot_size=100, allow_short=False, ...)
Market(name="Crypto", t_plus=0, allow_short=True, ...)
```

`markets.A_STOCK` 和 `markets.CRYPTO` 只是预设对象。旧的 `ChinaAStockMarket()`、`CryptoMarket()` 保留为兼容工厂，不再作为推荐写法。

### 当前 Market 特征

|字段|说明|
|---|---|
|`name`|市场名称，用于表达配置意图|
|`allow_short`|是否允许净空头|
|`t_plus`|当前只支持 `0` 和 `1`|
|`lot_size`|最小交易数量单位|
|`tick_size`|价格最小变动单位|
|`min_qty`|最小下单数量|
|`min_notional`|最小名义金额|
|`require_dt`|是否要求订单必须带真实时间|
|`weekdays_only`|是否只允许工作日|
|`trading_sessions`|日内交易时间段|
|`allow_daily_bar`|是否允许 `00:00:00` 代表日线 bar|

当前 `Market` 是最小配置对象，不引入复杂规则类。将来若真实需求出现，再考虑 per-symbol 最小交易单位、交易日历、涨跌停等扩展。

### A 股规则

`markets.A_STOCK` 当前实现：

- 工作日交易。
- 交易时间 `09:30-11:30`、`13:00-15:00`。
- 日线数据的 `00:00:00` 视为可交易。
- `require_dt=True`，直接手动调用 broker 时必须传 `price_dt`。
- `lot_size=100`。
- `tick_size=0.01`。
- `allow_short=False`。
- `t_plus=1`，同日买入持仓锁定，下一交易日解锁。

`close_position()` 和 `close_portfolio()` 在 T+1 下默认表达“全平”意图，不能全平时返回失败，不静默部分平仓。

## 函数式退出规则

函数式止盈止损已实现。常规止盈止损只是函数式条件的特殊形式。

```python
from minbt import stop_loss_pct, take_profit_pct

def on_init(self):
    self.broker.add_exit_rule("BTCUSDT", stop_loss_pct(0.05))
    self.broker.add_exit_rule("BTCUSDT", take_profit_pct(0.10))
```

自定义退出条件：

```python
def max_drawdown_exit(ctx):
    peak = ctx.state.get("peak", ctx.price)
    ctx.state["peak"] = max(peak, ctx.price)
    return ctx.position.size > 0 and ctx.price < ctx.state["peak"] * 0.92

def on_init(self):
    self.broker.add_exit_rule(
        "BTCUSDT",
        name="max_drawdown",
        condition=max_drawdown_exit,
        state={},
    )
```

分仓退出规则：

```python
self.broker.add_exit_rule("BTCUSDT", stop_loss_pct(0.05), portfolio="trend")
```

退出规则在每个 `on_bars` 前检查，使用当前最新价市价平仓。不模拟同一根 bar 内的高低价路径。

## 限价单边界

README 如果提到“支持限价单”，必须明确当前未实现。当前代码中：

```python
Broker.submit_limit_order(...)
Broker.cancel_order(...)
Broker.submit_stop_order(...)
Broker.submit_trailing_stop_order(...)
```

均为 `NotImplementedError`。

未来最小限价单设计应满足：

- 用户可以提交 pending limit order。
- broker 在 bar 更新后基于 high/low 判断是否成交。
- 成交仍必须经过 `Market.validate_order(...)`。
- `cancel_order(order_id)` 可以取消未成交订单。
- 不模拟队列位置、部分成交和逐笔撮合，除非真实需求出现。

## 内部实现边界

Broker 负责：

- 接收交易意图。
- 读取或更新最新价格。
- 调用 `Market` 校验订单。
- 调用 `Portfolio` 执行成交。
- 调用 `Market` 维护 T+1 锁定等市场状态。

Portfolio 负责：

- 现金、保证金、持仓、盈亏。
- 全仓/逐仓的基础账户状态。
- 订单成交对现金和持仓的影响。

Position 负责：

- `size`、成本价、保证金、未实现盈亏。
- `available_size`、`locked_size`。
- T+1 锁定批次的记录和解锁。

Market 负责：

- 交易时间校验。
- T+0/T+1。
- lot size、tick size。
- 是否允许做空。
- 最小数量和最小名义金额。

## 后续优先级

1. 先保持市价回测路径稳定。
2. 再做最小限价单。
3. 只有真实策略需要时，才支持 per-symbol 市场规则。
4. 只有真实数据需要时，才扩展 `on_books/on_trades/on_news`。
