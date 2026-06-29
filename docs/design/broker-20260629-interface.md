# Broker 接口完整设计

## 状态

目标设计稿。

本文件用于完整定义 broker 的用户接口和内部接口边界。当前代码可能已有部分实现，但后续实现应以本文件的接口语义为准。

## 设计目标

minbt 的目标是最简、方便、快捷的回测系统，不是完整交易所模拟器。

Broker 的用户接口必须贴近真实交易场景：

1. 策略在 `on_bars(dt, bars)` 中读取行情。
2. 策略通过 `self.broker` 表达交易意图。
3. Broker 执行交易、维护账户、检查市场规则和退出条件。
4. 用户不需要理解撮合队列、订单状态机、T+1 锁定批次等内部细节。

核心使用模型：

```python
class MyStrategy(Strategy):
    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["close"]
        self.broker.order_target_percent(
            "BTCUSDT",
            0.8,
            price=price,
            stop_loss=price * 0.95,
            take_profit=price * 1.10,
        )
```

## 接口分层

### 用户接口

用户接口面向策略作者，应该表达真实意图：

- 创建 broker。
- 分仓。
- 下单。
- 调目标仓位。
- 设置、修改、清除退出条件。
- 查询现金、权益、持仓和退出条件。

### 高级用户接口

高级接口仍面向策略作者，但用于非标准退出逻辑：

- 增加自定义退出条件。
- 清除自定义退出条件。

高级接口不应该污染常规下单路径。

### 内部接口

内部接口面向 broker、portfolio、market 和 exchange 的协作：

- 更新时间。
- 更新最新价格。
- 校验订单。
- 规范化数量。
- 执行成交。
- 检查退出条件。
- 维护 T+1 锁定。

内部接口可以更精确，但不应作为 README 主路径示例。

## 命名规范

|概念|命名|说明|
|---|---|---|
|订单增量|`qty`|本次买入或卖出多少，可正可负|
|当前持仓|`size`|账户当前净持仓，可正可负|
|目标持仓|`target_size`|希望调到的净持仓|
|目标名义金额|`target_value`|希望调到的持仓名义金额|
|目标权重|`target_percent`|希望调到组合权益的比例|
|组合|`portfolio`|用户接口中的组合名称|
|内部组合标识|`portfolio_id`|内部或兼容参数，不作为新用户主接口|
|止损触发价|`stop_loss`|标准价格型退出条件|
|止盈触发价|`take_profit`|标准价格型退出条件|
|自定义退出条件|`condition`|函数型退出条件，不叫止盈或止损|

关键原则：

1. `stop_loss` 和 `take_profit` 只表示标准价格触发价。
2. 函数型条件统一叫 `condition`，它是退出条件，不强行区分止盈或止损。
3. 不设计 `stop_loss=my_func` 或 `take_profit=my_func` 作为推荐接口。

## Broker 创建接口

### 推荐签名

```python
Broker(
    initial_cash: float,
    fee_rate: float,
    *,
    market: Market | None = None,
    leverage: float = 1.0,
    margin_mode: Literal["cross", "isolated"] = "cross",
    warning_margin_level: float = 0.2,
    min_margin_level: float = 0.1,
    logger=None,
)
```

### 语义

- `initial_cash` 表示 broker 初始现金。
- 默认创建 `main` portfolio。
- 默认全部现金进入 `main`。
- `fee_rate` 是成交手续费率。
- `market` 是市场特征配置；不传则使用默认 T+0 市场。
- `leverage` 是默认杠杆。
- `margin_mode` 定义保证金模式。

### 不推荐参数

以下参数仅作为兼容入口，不进入推荐接口：

```python
portfolio_cash
portfolio_id
```

理由：

- `portfolio_cash` 会让用户同时理解总现金、主组合现金、未分配现金，增加认知负担。
- `portfolio_id` 是内部标识命名，新用户应使用 `portfolio`。

## 分仓接口

### 添加 portfolio

```python
broker.add_portfolio(name: str, cash: float) -> None
```

语义：

- 从 `main` 的可用现金划拨 `cash` 创建新 portfolio。
- `name` 必须唯一。
- `cash` 必须大于 0。
- `cash` 不得超过 `main` 的可用现金。
- 新 portfolio 继承 broker 的 market、fee、leverage 和 margin 配置。

示例：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001)
broker.add_portfolio("trend", cash=60_000)
broker.add_portfolio("mean_reversion", cash=20_000)
```

### 关闭 portfolio

```python
broker.close_portfolio(portfolio: str = "main") -> bool
```

语义：

- 尝试平掉该 portfolio 的全部持仓。
- 全部持仓都能平仓时才关闭 portfolio。
- 任一持仓因市场规则、T+1、缺少价格等原因无法平仓，则返回 `False`，状态不应被破坏。
- 非 `main` portfolio 关闭后，剩余现金回到 `main`。

## 市价单接口

### 推荐签名

```python
broker.submit_market_order(
    symbol: str,
    qty: float,
    price: float | None = None,
    *,
    leverage: float | None = None,
    price_dt=None,
    portfolio: str | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> bool
```

### 语义

- `qty > 0`：买入或增加多头。
- `qty < 0`：卖出或增加空头。
- `qty == 0`：无效。
- `price` 为空时使用 broker 最新价。
- 显式传入 `price` 时，broker 可以先更新该 symbol 的最新价再成交。
- `portfolio` 为空时使用 `main`。
- `stop_loss` 和 `take_profit` 是成交后绑定到净持仓的标准价格型退出条件。
- 下单失败时不应设置退出条件。

示例：

```python
self.broker.submit_market_order(
    "BTCUSDT",
    qty=1,
    price=price,
    stop_loss=price * 0.95,
    take_profit=price * 1.10,
)
```

## 目标仓位接口

目标仓位接口是 minbt 的主路径，不是语法糖。真实策略经常表达“调到多少”，而不是“这次增量多少”。

### 目标数量

```python
broker.order_target_size(
    symbol: str,
    target_size: float,
    price: float | None = None,
    *,
    leverage: float | None = None,
    price_dt=None,
    portfolio: str | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> bool
```

### 目标名义金额

```python
broker.order_target_value(
    symbol: str,
    target_value: float,
    price: float | None = None,
    *,
    leverage: float | None = None,
    price_dt=None,
    portfolio: str | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> bool
```

### 目标权重

```python
broker.order_target_percent(
    symbol: str,
    target_percent: float,
    price: float | None = None,
    *,
    leverage: float | None = None,
    price_dt=None,
    portfolio: str | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> bool
```

### 语义

- `target_size` 是目标净持仓。
- `target_value` 是目标名义金额。
- `target_percent` 是目标 portfolio 权益比例。
- 三个接口都通过内部市价单执行增量订单。
- 三个接口都必须经过 market 校验。
- 三个接口都支持订单成交后设置标准价格型退出条件。

示例：

```python
self.broker.order_target_percent(
    "BTCUSDT",
    0.8,
    price=price,
    stop_loss=price * 0.95,
    take_profit=price * 1.10,
)
```

## 平仓接口

### 平掉单个持仓

```python
broker.close_position(
    symbol: str,
    price: float | None = None,
    *,
    price_dt=None,
    portfolio: str | None = None,
) -> bool
```

语义：

- 表达“全平该 symbol 净持仓”的意图。
- 无持仓时返回 `False`。
- 如果市场规则不允许全平，例如 A 股 T+1 可平数量不足，返回 `False`。
- 不做静默部分平仓。
- 平仓成功后应清除该持仓的 position-scoped 标准退出条件。

### 平掉所有持仓

暂不设计 `close_all_positions()` 作为用户主接口。

理由：

- `close_portfolio(...)` 已覆盖关闭组合场景。
- 批量平仓需要更明确的失败语义，避免部分平仓后状态不清。

如未来需要，应设计为：

```python
broker.close_positions(portfolio: str | None = None) -> CloseResult
```

而不是简单返回 bool。

## 标准退出接口

标准退出接口用于常规止盈止损。它只接受价格，不接受函数。

### 设置或修改

```python
broker.set_exit(
    symbol: str,
    *,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    portfolio: str | None = None,
) -> None
```

语义：

- 设置或修改该 `portfolio + symbol` 当前净持仓的标准退出条件。
- `stop_loss` 为空表示不修改止损。
- `take_profit` 为空表示不修改止盈。
- 若两者都为空，应视为无操作或抛出 `ValueError`；推荐抛出 `ValueError`，避免静默误用。
- 若无持仓时调用，推荐允许预设还是拒绝需要明确；MVP 推荐拒绝，减少隐藏状态。

触发语义：

|持仓方向|止损触发|止盈触发|
|---|---|---|
|多头 `size > 0`|`price <= stop_loss`|`price >= take_profit`|
|空头 `size < 0`|`price >= stop_loss`|`price <= take_profit`|

### 清除

```python
broker.clear_exit(
    symbol: str,
    *,
    stop_loss: bool = True,
    take_profit: bool = True,
    portfolio: str | None = None,
) -> None
```

语义：

- 默认清除标准止损和标准止盈。
- 可以只清一边：

```python
broker.clear_exit("BTCUSDT", take_profit=False)
```

表示只清除止损。

### 查询

```python
broker.get_exit(
    symbol: str,
    *,
    portfolio: str | None = None,
) -> ExitConfig | None
```

返回结构：

```python
@dataclass
class ExitConfig:
    symbol: str
    portfolio: str
    stop_loss: float | None
    take_profit: float | None
```

查询接口是必要的，因为真实策略会根据已有止损止盈决定是否上移止损、撤掉止盈或重新设置退出条件。

## 自定义退出条件接口

自定义退出条件不是止盈，也不是止损。它就是退出条件。

### 添加

```python
broker.add_exit(
    symbol: str,
    *,
    condition: Callable[[ExitContext], bool],
    name: str | None = None,
    state: dict | Callable[[], dict] | None = None,
    portfolio: str | None = None,
) -> ExitRule
```

语义：

- `condition(ctx) -> bool` 返回 `True` 时退出。
- 多个退出条件是 OR 关系。
- `name` 用于日志和调试。
- `state` 用于保存条件内部状态。
- 该接口用于移动止损、时间止损、信号反转、波动率退出等高级逻辑。

示例：

```python
def trailing_exit(ctx):
    peak = ctx.state.get("peak", ctx.price)
    peak = max(peak, ctx.price)
    ctx.state["peak"] = peak
    return ctx.price <= peak * 0.92

self.broker.add_exit(
    "BTCUSDT",
    name="trailing_exit",
    condition=trailing_exit,
    state={},
)
```

### 清除自定义退出条件

```python
broker.clear_custom_exits(
    symbol: str | None = None,
    *,
    name: str | None = None,
    portfolio: str | None = None,
) -> None
```

语义：

- 不传 `symbol` 时清除指定 portfolio 下所有自定义退出条件。
- 传 `name` 时只清除同名条件。
- 不影响标准 `stop_loss/take_profit`。

### 为什么不把 condition 放进 set_exit

不推荐：

```python
broker.set_exit(
    symbol,
    stop_loss=95,
    take_profit=110,
    condition=my_exit_condition,
)
```

理由：

- `stop_loss/take_profit` 是标准价格型退出条件。
- `condition` 是任意退出条件。
- 三者放在同一个接口中，会让用户困惑覆盖关系、优先级和清除语义。

推荐拆分：

```python
broker.set_exit(symbol, stop_loss=95, take_profit=110)
broker.add_exit(symbol, condition=my_exit_condition, name="my_exit")
```

## 退出条件触发模型

### 检查时机

默认在每个 `on_bars` 前检查：

```text
Exchange 更新当前 bar 全部 symbol 最新价
Broker 检查退出条件
Strategy.on_bars(dt, bars)
```

这样策略在 `on_bars` 中看到的是退出条件处理后的账户状态。

### 触发价格

MVP 默认使用当前 bar 的 `close` 触发。

不默认使用 high/low，原因：

- 同一根 bar 同时触发止盈和止损时，先后顺序不可知。
- 使用 high/low 容易制造假精度。
- minbt 当前目标是方便快捷回测，不是逐笔撮合。

未来如支持 OHLC 触发，必须显式配置：

```python
Broker(..., exit_trigger="close")
Broker(..., exit_trigger="ohlc", intrabar_priority="stop_first")
```

但这不进入当前 MVP。

### 多条件关系

同一个 `portfolio + symbol` 可以同时有：

- 标准止损。
- 标准止盈。
- 一个或多个自定义退出条件。

关系：

- 任一条件触发即退出。
- 标准止损和标准止盈没有优先级；在 close 触发模型下同一价格通常不会同时满足。
- 自定义条件按注册顺序检查。
- 触发成功后，清除该 symbol 的标准退出条件。
- 自定义退出条件是否清除由接口语义决定；MVP 推荐 position-scoped，自定义条件触发后也清除该 symbol 的自定义退出条件。

## 持仓变化与退出条件生命周期

### 开仓

下单或目标仓位接口带 `stop_loss/take_profit` 时：

- 订单成交成功。
- 持仓非空。
- 设置标准退出条件。

订单失败时：

- 不设置退出条件。

### 加仓

同方向加仓时：

- 如果新订单显式传入 `stop_loss/take_profit`，更新标准退出条件。
- 如果新订单未传入，保留原标准退出条件。

### 减仓

同方向减仓但持仓仍非空时：

- 默认保留标准退出条件。
- 如果显式传入新的 `stop_loss/take_profit`，更新。

### 全平

持仓归零时：

- 清除标准退出条件。
- 清除 position-scoped 自定义退出条件。

### 反手

从多头变空头或从空头变多头时：

- 清除旧方向退出条件。
- 如果反手订单带 `stop_loss/take_profit`，按新方向设置。
- 如果反手订单未带退出条件，反手后无标准退出条件。

## 查询接口

### 权益与现金

```python
broker.get_total_equity() -> float
broker.get_all_portfolio_equity() -> float
broker.get_equity(portfolio: str | None = None) -> float
broker.get_cash(include_locked: bool = False, *, portfolio: str | None = None) -> float
```

语义：

- `get_total_equity()` 返回全部 portfolio 权益加兼容层未分配现金。
- `get_all_portfolio_equity()` 返回全部 portfolio 权益。
- `get_equity()` 默认返回 `main`。
- `get_cash()` 默认返回 `main` 可用现金。

### 持仓

```python
broker.get_position(symbol: str, *, portfolio: str | None = None, create_if_missing: bool = False) -> Position | None
broker.get_position_size(symbol: str, *, portfolio: str | None = None) -> float
broker.get_position_sizes(*, portfolio: str | None = None) -> dict[str, float]
broker.get_positions(*, portfolio: str | None = None) -> dict[str, Position]
```

推荐用户查询：

- `get_position_size(...)`
- `get_position_sizes(...)`
- `get_positions(...)`

`get_position(..., create_if_missing=True)` 是内部兼容能力，不推荐用户主路径使用。

### 行情

```python
broker.get_last_price(symbol: str, return_dt: bool = False)
broker.get_market_price(symbol: str, return_dt: bool = False)
```

`get_market_price` 仅作为兼容别名；推荐文档使用 `get_last_price`。

### Portfolio 列表

```python
broker.get_portfolios() -> list[str]
```

返回当前 portfolio 名称列表。

## 限价单接口边界

当前不进入 MVP，但接口应预留清晰方向。

### 未来接口

```python
broker.submit_limit_order(
    symbol: str,
    qty: float,
    limit_price: float,
    *,
    portfolio: str | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> Order
```

```python
broker.cancel_order(order_id: str, *, portfolio: str | None = None) -> bool
```

设计原则：

- 限价单是 pending order。
- 成交后才能绑定标准退出条件。
- 不模拟队列位置和部分成交，除非真实需求出现。
- 使用 high/low 成交时必须定义同一根 bar 的触发顺序。

## Market 用户接口

### 推荐

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001, market=markets.CRYPTO)
broker = Broker(initial_cash=100_000, fee_rate=0.0003, market=markets.A_STOCK)
```

自定义：

```python
market = Market(
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

### 不推荐

```python
ChinaAStockMarket()
CryptoMarket()
SimpleMarket()
```

这些只作为兼容入口存在。

## 内部接口契约

### Broker 内部

```python
Broker.on_new_price(symbol, price, dt=None)
Broker.check_exit_rules(dt=None, data=None)
Broker._resolve_portfolio(portfolio=None, portfolio_id=None)
Broker._require_portfolio(portfolio_id)
```

语义：

- `on_new_price` 由 Exchange 或 broker 显式价格下单路径调用。
- `check_exit_rules` 由 Exchange 在策略回调前调用。
- `_resolve_portfolio` 处理推荐 `portfolio` 和兼容 `portfolio_id`。
- `_require_portfolio` 统一做组合存在性检查。

### Market 内部

```python
Market.is_trading_time(dt) -> bool
Market.trading_day(dt)
Market.on_new_dt(broker, dt) -> None
Market.normalize_order_qty(broker, symbol, qty, price=None, portfolio_id="main") -> float
Market.validate_order(broker, symbol, qty, price, dt=None, portfolio_id="main") -> OrderValidation
Market.on_order_filled(broker, symbol, qty, price, dt=None, portfolio_id="main") -> None
```

语义：

- Broker 每笔订单都应经过 `Market.validate_order`。
- 目标仓位产生的数量应经过 `Market.normalize_order_qty`。
- T+1 等市场状态由 `Market.on_new_dt` 和 `Market.on_order_filled` 维护。

### Portfolio 内部

```python
Portfolio.submit_order(symbol, qty, price, leverage=None, price_dt=None) -> bool
Portfolio.on_new_price(symbol, price, dt=None)
Portfolio.get_position(symbol, create_if_missing=False)
```

语义：

- Portfolio 只处理账户状态，不判断市场是否允许交易。
- 市场规则属于 Market。
- 用户不应直接调用 Portfolio 下单。

## 返回值与错误语义

### 返回 bool 的接口

以下接口返回 `bool`：

- `submit_market_order`
- `order_target_size`
- `order_target_value`
- `order_target_percent`
- `close_position`
- `close_portfolio`

语义：

- `True` 表示交易或关闭实际完成。
- `False` 表示因为市场规则、资金、无持仓等业务原因未执行。
- 参数错误、portfolio 不存在、价格缺失等编程错误应抛异常。

### 抛异常的场景

应抛异常：

- `initial_cash <= 0`。
- `fee_rate` 非法。
- `portfolio` 不存在。
- `price` 缺失且 broker 没有最新价。
- `qty == 0` 作为用户参数传入。
- `set_exit` 两个参数都为空。
- `stop_loss/take_profit` 价格非正。

可返回 `False`：

- 资金不足。
- 市场规则拒单。
- T+1 不允许平仓。
- 无持仓可平。

## 当前实现与目标设计差异

当前代码已有较多能力，但仍有几点需要后续对齐：

1. 当前 `set_exit` 允许 `stop_loss` 或 `take_profit` 传 callable；目标设计中函数型退出应使用 `add_exit`。
2. 当前函数式接口名是 `add_exit_rule`；目标设计推荐用户名为 `add_exit`，旧名可保留兼容。
3. 当前还没有 `get_exit(...)`。
4. 当前 `clear_exit(...)` 不能只清止损或只清止盈。
5. 当前持仓归零、反手时退出条件生命周期需要进一步系统化。
6. 当前 `submit_limit_order/cancel_order/submit_stop_order/submit_trailing_stop_order` 仍是未实现占位。

## 推荐实施顺序

1. 先补 `get_exit(...)` 和标准退出配置结构。
2. 调整 `set_exit(...)`，只接受价格型 `stop_loss/take_profit`。
3. 增加 `add_exit(...)`，保留 `add_exit_rule(...)` 作为兼容别名。
4. 完善 `clear_exit(...)`，支持只清止损或只清止盈。
5. 系统处理全平和反手时的退出条件清理。
6. 最后再考虑最小限价单。
