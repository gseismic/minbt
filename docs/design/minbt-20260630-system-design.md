# minbt 系统设计稿

## 状态

当前有效设计。

本设计合并并替代以下旧稿：

- `DESIGN-001-broker-account-market-api.md`
- `DESIGN-002-data-feeds-and-callbacks.md`
- `broker-20260629-interface.md`

旧稿删除，避免后续继续引用过期接口。

本文以当前代码为事实基础，同时给出目标接口。凡是目标接口和当前代码不一致，均在“当前实现差异与迁移顺序”中明确。

## 总目标

minbt 的目标是最简、方便、快捷的回测系统，不是完整交易所模拟器。

用户真实场景是：

1. 准备历史数据。
2. 在策略回调里读取同一时间截面的行情。
3. 调用 `self.broker` 完成交易。
4. 查看资金、持仓和回测结果。

稳定主路径：

```python
class MyStrategy(Strategy):
    def on_init(self):
        self.symbol = "BTCUSDT"

    def on_bars(self, dt, bars):
        price = bars[self.symbol]["close"]
        self.broker.order_target_percent(self.symbol, 0.8, price=price)
```

不追求：

- 完整订单簿撮合。
- 队列位置、部分成交、逐笔撮合。
- 复杂事件总线。
- 通用 DSL。
- 完整账户快照初始化。
- 初始持仓的杠杆、保证金、锁定批次配置。

## 接口分层原则

### 用户接口

用户接口面向策略作者，目标是低认知负担表达真实意图。

推荐用户只需要理解这些概念：

|概念|说明|
|---|---|
|`Exchange`|提供历史数据并推进回测时钟|
|`Strategy`|写策略逻辑|
|`on_bars(dt, bars)`|当前时间截面的 bars 数据|
|`Broker`|唯一交易入口|
|`Order`|用户提交的一笔交易意图及其句柄|
|`portfolio`|分仓名称|
|`Market`|市场特征配置|

用户接口不暴露：

- pending order 状态机细节。
- T+1 锁定批次细节。
- Portfolio 内部现金对象。
- Position 内部保证金计算过程。
- 撮合队列和成交路径假设。

### 高级用户接口

高级用户接口允许表达更复杂但仍贴近策略语义的需求：

- `broker.add_portfolio(...)`
- `broker.set_exit(order_id, ...)`
- `broker.add_exit(order_id, condition=...)`
- 自定义 `Market(...)` 特征。

这些接口仍然是用户接口，不应要求用户理解内部状态机。

### 内部接口

内部接口面向系统模块，目标是正确性、可维护性和可测试性。

内部接口包括：

- `Market.validate_order(...)`
- `Market.on_new_dt(...)`
- `Market.on_order_filled(...)`
- `Portfolio.submit_order(...)`
- `Position.lock_size(...)`
- `Position.unlock_before(...)`

内部接口可以贴近实现模型，但必须明确状态边界、错误语义和可测试契约。

## 全局命名规范

|概念|推荐命名|说明|
|---|---|---|
|标的|`symbol`|交易标的代码|
|订单增量|`qty`|本次买入或卖出多少，可正可负|
|当前持仓|`size`|账户当前净持仓，可正可负|
|可平持仓|`available_size`|当前允许平仓的数量，非负|
|锁定持仓|`locked_size`|当前不可平仓的数量，非负|
|目标持仓|`target_size`|希望调到多少净持仓|
|目标名义金额|`target_value`|希望调到多少名义金额|
|目标权重|`target_percent`|希望调到组合权益的多少比例|
|组合名|`portfolio`|用户接口使用的分仓名称|
|组合内部标识|`portfolio_id`|内部和兼容参数，新代码不推荐|
|订单对象|`order`|用户提交交易后的句柄|
|订单 ID|`order_id`|用于修改该订单关联退出条件|
|止损触发价|`stop_loss_price`|标准价格型退出条件|
|止盈触发价|`take_profit_price`|标准价格型退出条件|
|百分比移动止损|`trailing_stop_pct`|按最高价/最低价回撤百分比退出|
|固定金额移动止损|`trailing_stop_amount`|按最高价/最低价回撤固定金额退出|

命名约束：

1. `qty` 只用于订单增量。
2. `size` 只用于持仓状态。
3. 不用 `amount` 表示订单数量，避免和现金金额混淆。
4. 不用 `sl_price/tp_price` 作为用户接口，缩写降低可读性。
5. 不用 `stop_loss=my_func` 或 `take_profit=my_func` 表示函数型退出条件。
6. 函数型退出条件统一叫退出条件，不强行区分止盈或止损。
7. 用户接口使用 `portfolio`，内部兼容可以继续接受 `portfolio_id`。

## 数据接入与策略回调

### 当前 MVP

当前只支持 bars 数据。

推荐数据入口：

```python
exchange.set_bars(data, date_key="dt")
```

兼容入口：

```python
exchange.set_data(data, date_key="dt")
```

`set_data(...)` 在文档里只解释为 bars 兼容入口，不再作为推荐用户接口。

### bars 输入结构

bars 输入至少包含：

```text
dt
symbol
close
```

可选包含：

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

当 `date_key` 不为 `None`：

- 数据按 `date_key` 和 `symbol` 稳定排序。
- 同一 `(dt, symbol)` 不能重复。
- 每次回调传入同一 `dt` 下完整截面。

当 `date_key is None`：

- 使用行号作为时间。
- 只允许单标的数据。

### 策略回调

唯一推荐用户回调：

```python
class Strategy:
    def on_bars(self, dt, bars):
        pass
```

`bars` 永远是：

```python
dict[str, bar]
```

单标的也是多标的特例：

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
        self.broker.order_target_percent(symbol, 0.25, price=bar["close"])
```

不提供单标的专用结构，不引入 `tick.price()` 这类包装对象。

### 兼容回调

当前代码仍保留：

```python
def on_data(self, data):
    ...

def on_bar(self, dt, rows_by_symbol):
    ...
```

它们只作为兼容接口。

推荐文档、README 和 examples 不再展示 `on_data/on_bar`。

兼容调用顺序：

1. 如果策略重写 `on_bars`，只调用 `on_bars`。
2. 否则兼容旧 `on_data/on_bar`。

### 未来数据类型

未来只有真实需求出现时，才扩展其他同型回调：

```python
def on_books(self, dt, books):
    ...

def on_trades(self, dt, trades):
    ...

def on_news(self, dt, news):
    ...
```

所有 `on_xx` 遵循同一规则：

> `on_xx(self, dt, data)` 表示在同一个回测时间 `dt`，收到某一类数据的完整时间切片。

推荐命名：

- 盘口类数据用 `on_books`，不使用过长的 `on_orderbooks`。
- 交易明细用 `on_trades`。
- 新闻用 `on_news`。

MVP 不实现多数据源调度，也不引入通用 `on_event(event)`。

## 回测时钟与执行顺序

当前 bars 回测顺序：

1. Exchange 进入下一个 `dt`。
2. Exchange 收集当前 `dt` 下所有 symbol 的 bars。
3. Exchange 先整体更新 broker 最新价。
4. Broker 检查退出条件。
5. Strategy 收到 `on_bars(dt, bars)`。
6. 记录权益和持仓历史。

关键约束：

- 多标的策略必须在同一 `dt` 看到完整截面。
- Broker 在策略回调前已看到当前 `dt` 下所有 symbol 的最新价格。
- 退出条件在策略回调前处理，因此策略看到的是退出处理后的账户状态。

当前不模拟同一根 bar 内的路径顺序。若同一根 bar 内同时达到止盈和止损，MVP 不做高低价路径推断。

## Broker 创建接口

推荐：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001)
```

完整推荐签名：

```python
broker = Broker(
    initial_cash: float,
    fee_rate: float,
    *,
    leverage: float = 1.0,
    margin_mode: Literal["cross", "isolated"] = "cross",
    warning_margin_level: float = 0.2,
    min_margin_level: float = 0.1,
    market: Market | None = None,
    logger=None,
)
```

语义：

- `initial_cash` 只表示 broker 初始现金。
- 默认创建 `main` portfolio。
- 默认全部现金进入 `main`。
- 默认不支持初始持仓。
- 默认市场是 `markets.DEFAULT`。

不推荐用户使用：

```python
Broker(..., portfolio_cash=...)
Broker(..., portfolio_id=...)
Broker(..., initial_positions=...)
```

其中：

- `portfolio_cash` 和 `portfolio_id` 是当前代码里的兼容/历史参数，目标用户接口不保留。
- `initial_positions` 不进入 MVP，避免引入成本价、杠杆、保证金、可用数量和锁定批次的复杂初始化语义。

## 分仓接口

推荐：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001)
broker.add_portfolio("trend", cash=60_000)
broker.add_portfolio("mean_reversion", cash=20_000)
```

语义：

- 默认组合名是 `main`。
- `add_portfolio(name, cash)` 从 `main` 可用现金划拨资金创建新组合。
- 分仓只做资金和持仓隔离，不是独立 broker。
- 所有 portfolio 共享同一个 broker 的 market、fee、杠杆配置。

交易时指定组合：

```python
self.broker.order_target_percent("BTCUSDT", 0.8, price=price, portfolio="trend")
self.broker.submit_market_order("ETHUSDT", qty=1, price=price, portfolio="mean_reversion")
```

查询：

```python
broker.get_equity()
broker.get_equity(portfolio="trend")
broker.get_cash(portfolio="trend")
broker.get_position_size("BTCUSDT", portfolio="trend")
broker.get_positions(portfolio="trend")
broker.get_total_equity()
```

兼容但不推荐：

```python
broker.add_sub_portfolio("old", initial_cash=10_000)
broker.submit_market_order("BTCUSDT", qty=1, portfolio_id="old")
```

原因：

- `sub_portfolio` 暗示层级，但实际只是并列分仓。
- `portfolio_id` 暴露内部标识，不符合用户心智模型。

## Market 市场特征

### 推荐写法

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

自定义市场：

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

### 为什么是特征而不是市场类

不推荐：

```python
ChinaAStockMarket()
CryptoMarket()
```

推荐：

```python
Market(name="AStock", t_plus=1, lot_size=100, allow_short=False, ...)
Market(name="Crypto", t_plus=0, allow_short=True, ...)
```

理由：

- A 股、加密资产、本地模拟市场本质上是规则特征不同。
- 用户不需要理解继承体系。
- 预设对象 `markets.A_STOCK` 和 `markets.CRYPTO` 足够表达常用场景。
- 后续增加最小交易额、tick、交易时间等规则时，只扩展特征字段。

当前代码中的 `SimpleMarket()`、`CryptoMarket()`、`ChinaAStockMarket()` 仅作为兼容工厂保留，不作为推荐用户接口。

### 当前 Market 字段

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

### A 股预设

`markets.A_STOCK` 语义：

- 工作日交易。
- 交易时间 `09:30-11:30`、`13:00-15:00`。
- 日线数据的 `00:00:00` 视为可交易。
- `require_dt=True`。
- `lot_size=100`。
- `tick_size=0.01`。
- `allow_short=False`。
- `t_plus=1`。

T+1 规则：

- 当日买入的数量进入 `locked_size`。
- 下一交易日解锁。
- 平仓时检查 `available_size`。
- `close_position()` 表达全平意图；不能全平则失败，不静默部分平。

### 后续可能扩展

后续按真实需求再增加：

- per-symbol `lot_size`、`tick_size`、`min_qty`、`min_notional`。
- 交易日历。
- 涨跌停。
- 手续费和滑点模型。

不在 MVP 里预先设计复杂市场类层级。

## Order 订单句柄

### 为什么使用 Order

真实交易中，用户提交的是订单，并且常常在订单上附带止盈止损。中途修改时，用户也会说“改这笔订单的退出条件”。

因此目标用户接口使用 `Order`，不使用 `Trade` 作为用户概念。

概念边界：

|概念|受众|说明|
|---|---|---|
|`Order`|用户接口|用户提交的一笔交易意图和后续修改句柄|
|`Fill`|内部接口|订单实际成交记录|
|`Position`|查询/内部|当前净持仓状态|

MVP 可以只实现市价单立即成交，但仍返回 `Order`，这样退出条件可以绑定到订单句柄。

### 推荐结构

```python
@dataclass
class Order:
    id: str
    symbol: str
    qty: float
    portfolio: str
    status: Literal["filled", "rejected", "pending", "canceled"]
    order_type: Literal["market", "limit"]
    price: float | None
    limit_price: float | None
    created_dt: Any | None
    filled_dt: Any | None
    filled_qty: float
    avg_price: float | None
```

MVP 只需要最小字段：

- `id`
- `symbol`
- `qty`
- `portfolio`
- `status`
- `order_type`
- `avg_price`

### 最简净持仓边界

minbt 当前账户模型是每个 `(portfolio, symbol)` 一个净持仓，不做多批次独立持仓账本。

因此 MVP 中：

- `order_id` 是用户修改退出条件的句柄。
- 标准退出条件实际作用于该 `portfolio + symbol` 的当前净持仓。
- 同一 `portfolio + symbol` 上最新带退出条件的订单，可以覆盖当前净持仓的标准退出条件。
- 不支持同时为同一净持仓上的多个入场批次维护互相独立的止盈止损。

这比完整订单/持仓批次系统简单，符合当前最简目标。未来只有在真实需求明确需要“多笔入场分别止盈止损”时，再引入 lot/position batch。

## 市价单接口

推荐签名：

```python
broker.submit_market_order(
    symbol: str,
    qty: float,
    price: float | None = None,
    *,
    leverage: float | None = None,
    price_dt=None,
    portfolio: str | None = None,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    trailing_stop_pct: float | None = None,
    trailing_stop_amount: float | None = None,
) -> Order | None
```

语义：

- `qty > 0` 表示买入或增加多头。
- `qty < 0` 表示卖出或增加空头。
- `qty == 0` 是无效订单。
- `price=None` 时使用 broker 内部最新价。
- 显式传 `price` 时，broker 先更新最新价，再执行订单。
- 订单成功时返回 `Order`。
- 无效、被市场规则拒绝或资金不足时返回 `None`。
- 编程错误抛异常，例如找不到价格、portfolio 不存在、价格非正。

示例：

```python
order = self.broker.submit_market_order(
    "BTCUSDT",
    qty=1,
    price=price,
    stop_loss_price=price * 0.95,
    take_profit_price=price * 1.10,
    trailing_stop_pct=0.05,
)
```

## 目标仓位接口

目标仓位接口是快捷回测的核心用户接口，不是无意义语法糖。真实策略经常表达“把仓位调到多少”，而不是手动计算本次增量。

推荐签名：

```python
broker.order_target_size(
    symbol: str,
    target_size: float,
    price: float | None = None,
    *,
    leverage: float | None = None,
    price_dt=None,
    portfolio: str | None = None,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    trailing_stop_pct: float | None = None,
    trailing_stop_amount: float | None = None,
) -> Order | None

broker.order_target_value(
    symbol: str,
    target_value: float,
    price: float | None = None,
    *,
    leverage: float | None = None,
    price_dt=None,
    portfolio: str | None = None,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    trailing_stop_pct: float | None = None,
    trailing_stop_amount: float | None = None,
) -> Order | None

broker.order_target_percent(
    symbol: str,
    target_percent: float,
    price: float | None = None,
    *,
    leverage: float | None = None,
    price_dt=None,
    portfolio: str | None = None,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    trailing_stop_pct: float | None = None,
    trailing_stop_amount: float | None = None,
) -> Order | None
```

语义：

- `order_target_size` 调到目标净持仓。
- `order_target_value` 调到目标名义金额。
- `order_target_percent` 调到组合权益比例。
- 目标等于当前状态时返回 `None`。
- 最终仍转换为 broker 订单并经过 `Market.validate_order(...)`。
- 市场最小交易单位可以规范化目标买入数量。

示例：

```python
order = self.broker.order_target_percent(
    "BTCUSDT",
    0.8,
    price=price,
    stop_loss_price=price * 0.95,
    take_profit_price=price * 1.10,
)
```

## 平仓接口

平掉单个持仓：

```python
broker.close_position(
    symbol: str,
    price: float | None = None,
    *,
    price_dt=None,
    portfolio: str | None = None,
) -> Order | None
```

语义：

- 表达全平该 `portfolio + symbol` 当前净持仓。
- 没有持仓时返回 `None`。
- 缺少价格时抛异常或返回 `None`，实现需保持一致。
- T+1 市场可平数量不足时失败，不静默部分平仓。

关闭组合：

```python
broker.close_portfolio(portfolio: str) -> bool
```

语义：

- 先检查该组合所有仓位是否都能关闭。
- 任一仓位无法关闭，则整个关闭失败。
- 成功后平掉全部仓位，并将现金回到 `main`。
- 关闭 `main` 不是主路径，不建议普通用户使用。

## 标准退出条件

### 下单时设置

推荐把标准退出条件放在订单提交时：

```python
order = self.broker.order_target_percent(
    "BTCUSDT",
    0.8,
    price=price,
    stop_loss_price=price * 0.95,
    take_profit_price=price * 1.10,
    trailing_stop_pct=0.05,
)
```

参数语义：

|参数|说明|
|---|---|
|`stop_loss_price`|固定止损触发价|
|`take_profit_price`|固定止盈触发价|
|`trailing_stop_pct`|移动止损百分比回撤|
|`trailing_stop_amount`|移动止损固定金额回撤|

约束：

- `stop_loss_price` 和 `take_profit_price` 是价格，不是百分比。
- `trailing_stop_pct` 和 `trailing_stop_amount` 只能二选一。
- 固定止盈止损可以和移动止损同时存在。
- 函数型退出条件不放在 `stop_loss_price/take_profit_price` 中。

触发规则：

|方向|止损|止盈|
|---|---|---|
|多头 `size > 0`|`price <= stop_loss_price`|`price >= take_profit_price`|
|空头 `size < 0`|`price >= stop_loss_price`|`price <= take_profit_price`|

移动止损：

|方向|锚点|百分比触发|固定金额触发|
|---|---|---|---|
|多头|持仓后的最高价 `peak`|`price <= peak * (1 - trailing_stop_pct)`|`price <= peak - trailing_stop_amount`|
|空头|持仓后的最低价 `trough`|`price >= trough * (1 + trailing_stop_pct)`|`price >= trough + trailing_stop_amount`|

### 中途修改

真实交易中，止盈止损通常绑定订单，并允许中途修改。

目标接口：

```python
broker.set_exit(
    order_id: str,
    *,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    trailing_stop_pct: float | None = None,
    trailing_stop_amount: float | None = None,
) -> None
```

语义：

- `order_id` 指向用户提交订单返回的 `order.id`。
- `set_exit(...)` 只更新传入且非 `None` 的标准退出项。
- 未传或传 `None` 的标准退出项表示不修改该项。
- `trailing_stop_pct` 和 `trailing_stop_amount` 只能二选一。
- 修改移动止损时，锚点从当前最新价重新开始。
- 如果需要删除全部退出条件，使用 `clear_exit(order_id)`。
- MVP 不提供“只清除止盈”这类细分清除参数，避免过早复杂化。
- `order_id` 不存在或已失效时抛 `ValueError`。

示例：

```python
order = self.broker.order_target_percent(
    "BTCUSDT",
    0.8,
    price=price,
    stop_loss_price=price * 0.95,
    take_profit_price=price * 1.10,
)

self.broker.set_exit(
    order.id,
    stop_loss_price=price * 0.98,
    take_profit_price=price * 1.12,
)
```

清除：

```python
broker.clear_exit(order_id: str) -> None
```

语义：

- 清除该订单关联的所有退出条件。
- 如果只想修改其中一项，使用 `set_exit(order_id, ...)` 更新对应字段。

查询：

```python
broker.get_exit(order_id: str) -> ExitConfig | None
```

推荐结构：

```python
@dataclass
class ExitConfig:
    order_id: str
    symbol: str
    portfolio: str
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    trailing_stop_pct: float | None = None
    trailing_stop_amount: float | None = None
    trailing_anchor: float | None = None
```

## 函数型退出条件

函数型退出条件是高级接口，用来表达标准价格型止盈止损无法覆盖的退出逻辑。

不推荐：

```python
broker.order_target_percent(
    "BTCUSDT",
    0.8,
    price=price,
    stop_loss_price=95,
    take_profit_price=110,
    condition=my_exit_condition,
)
```

原因：

- `condition` 不区分止盈或止损，本质是退出条件。
- 与标准价格型参数混在一起会让接口含义变复杂。
- 下单主路径应该短，复杂逻辑应渐进展开。

推荐：

```python
order = self.broker.order_target_percent("BTCUSDT", 0.8, price=price)

self.broker.add_exit(
    order.id,
    name="max_drawdown",
    condition=max_drawdown_exit,
    state={},
)
```

目标签名：

```python
broker.add_exit(
    order_id: str,
    *,
    name: str | None = None,
    condition: Callable[[ExitContext], bool],
    state: dict | Callable[[], dict] | None = None,
) -> ExitRule
```

`ExitContext`：

```python
@dataclass
class ExitContext:
    order_id: str
    symbol: str
    dt: Any
    price: float
    position: Position
    broker: Broker
    portfolio: str
    data: Any = None
    state: dict | None = None
```

自定义示例：

```python
def max_drawdown_exit(ctx):
    peak = ctx.state.get("peak", ctx.price)
    peak = max(peak, ctx.price)
    ctx.state["peak"] = peak
    return ctx.position.size > 0 and ctx.price <= peak * 0.92

order = self.broker.order_target_percent("BTCUSDT", 0.8, price=price)
self.broker.add_exit(order.id, name="max_drawdown", condition=max_drawdown_exit, state={})
```

语义：

- 函数返回 `True` 表示退出当前 `portfolio + symbol` 净持仓。
- 触发后 broker 使用当前价格市价平仓。
- 函数型退出条件不叫 stop loss 或 take profit。
- `state` 用于保存条件自身状态。
- 不保证同一根 bar 内的真实触发路径。

辅助工厂可以保留为高级接口：

```python
stop_loss_pct(0.05)
take_profit_pct(0.10)
stop_loss_price(95)
take_profit_price(110)
```

但主路径优先使用订单参数 `stop_loss_price/take_profit_price`。

## 限价单边界

当前代码中的限价单接口尚未实现。

目标最小接口：

```python
order = broker.submit_limit_order(
    symbol: str,
    qty: float,
    limit_price: float,
    *,
    price_dt=None,
    portfolio: str | None = None,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    trailing_stop_pct: float | None = None,
    trailing_stop_amount: float | None = None,
) -> Order | None
```

取消：

```python
broker.cancel_order(order_id: str) -> bool
```

MVP 限价单规则：

- 提交后进入 pending。
- 每个新 bar 后，broker 用 `high/low` 判断是否触及限价。
- 成交价格默认使用 `limit_price`。
- 成交仍必须通过 `Market.validate_order(...)`。
- 不模拟队列位置。
- 不模拟部分成交。
- 不做逐笔成交路径。
- 限价单成交后才激活其退出条件。

暂不推荐暴露：

```python
submit_stop_order(...)
submit_trailing_stop_order(...)
```

因为当前真实需求可以由“订单附带退出条件”和未来最小限价单覆盖。等有明确入场止损单需求时再设计。

## 查询接口

### 订单

```python
broker.get_order(order_id: str) -> Order | None
broker.get_orders(*, portfolio: str | None = None, symbol: str | None = None) -> list[Order]
broker.get_active_order(symbol: str, *, portfolio: str | None = None) -> Order | None
```

MVP 中 `get_active_order` 返回该净持仓当前关联退出条件的订单。

### 权益和现金

```python
broker.get_equity(portfolio: str | None = None) -> float
broker.get_cash(portfolio: str | None = None, include_locked: bool = False) -> float
broker.get_total_equity() -> float
broker.get_portfolio_equity(portfolio: str | None = None) -> float
```

语义：

- 不传 `portfolio` 默认查询 `main`。
- `get_total_equity()` 汇总所有 portfolio。
- `include_locked=True` 表示现金查询包含锁定现金。

### 持仓

```python
broker.get_position(symbol: str, portfolio: str | None = None) -> Position | None
broker.get_position_size(symbol: str, portfolio: str | None = None) -> float
broker.get_position_sizes(portfolio: str | None = None) -> dict[str, float]
broker.get_positions(portfolio: str | None = None) -> dict[str, Position]
```

Position 用户可读字段：

- `symbol`
- `size`
- `cost_price`
- `last_price`
- `unrealized_pnl`
- `margin`
- `equity`
- `locked_size`
- `available_size`

### 行情

```python
broker.get_last_price(symbol: str, return_dt: bool = False)
exchange.get_last_price(symbol: str, return_dt: bool = False)
exchange.get_last_prices() -> dict[str, float]
exchange.get_current_dt()
```

## 内部接口契约

### Exchange

Exchange 负责：

- 持有历史数据。
- 按时间推进。
- 按同一 `dt` 聚合数据切片。
- 在策略回调前整体更新 broker 价格。
- 调用 broker 退出检查。
- 调用策略回调。
- 记录策略历史。

Exchange 不负责：

- 生成交易信号。
- 计算账户状态。
- 判断市场规则。
- 在 Strategy 上提供交易语法糖。

### Strategy

Strategy 负责：

- 在 `on_init` 初始化参数和状态。
- 在 `on_bars` 读取数据并调用 broker。
- 在 `on_finish` 做结果整理。

Strategy 不负责：

- 直接修改 Portfolio 或 Position。
- 直接绕过 broker 成交。
- 理解 Market 内部校验。

### Broker

Broker 负责：

- 接收用户交易意图。
- 解析 price 和 portfolio。
- 生成 Order。
- 调用 Market 校验。
- 调用 Portfolio 执行成交。
- 管理订单关联退出条件。
- 在新价格下检查退出条件。
- 管理多个 portfolio。

Broker 不负责：

- 存储历史行情。
- 生成策略信号。
- 模拟完整交易所撮合队列。

### Market

Market 负责：

- 交易时间校验。
- T+0/T+1。
- lot size、tick size。
- 是否允许做空。
- 最小数量和最小名义金额。
- 成交后的市场状态维护。

内部接口：

```python
Market.validate_order(broker, symbol, qty, price, dt=None, portfolio_id="main") -> OrderValidation
Market.normalize_order_qty(broker, symbol, qty, price=None, portfolio_id="main") -> float
Market.on_new_dt(broker, dt) -> None
Market.on_order_filled(broker, symbol, qty, price, dt=None, portfolio_id="main") -> None
```

### Portfolio

Portfolio 负责：

- 现金。
- 保证金。
- 当前净持仓。
- 全仓/逐仓基础账户状态。
- 成交对现金和持仓的影响。

Portfolio 不负责：

- 判断市场是否可交易。
- 管理多个分仓。
- 管理退出条件。
- 管理订单状态。

### Position

Position 负责：

- `size`。
- 成本价。
- 保证金。
- 未实现盈亏。
- `locked_size` 和 `available_size`。
- T+1 锁定批次。

Position 不负责：

- 判断订单是否应成交。
- 管理 portfolio 现金。
- 管理退出条件。

## 返回值与错误语义

### 推荐返回 `Order | None`

这些用户交易接口推荐返回 `Order | None`：

- `submit_market_order`
- `submit_limit_order`
- `order_target_size`
- `order_target_value`
- `order_target_percent`
- `close_position`

返回 `None` 表示正常业务失败或无交易：

- 目标仓位等于当前仓位。
- 市场规则拒绝。
- 资金不足。
- 持仓为空。

### 推荐返回 bool

这些批量或状态接口推荐返回 `bool`：

- `close_portfolio`
- `cancel_order`

原因是它们表达成功或失败，不需要继续绑定退出条件。

### 抛异常

以下属于编程错误，应抛异常：

- `price <= 0`。
- `qty == 0`。
- `portfolio` 不存在。
- `order_id` 不存在。
- `stop_loss_price/take_profit_price` 非正。
- `trailing_stop_pct/trailing_stop_amount` 非正。
- 同时设置 `trailing_stop_pct` 和 `trailing_stop_amount`。
- `date_key` 缺失。
- 多标的数据未提供 `date_key`。
- 同一 `(dt, symbol)` 重复。

## 当前实现状态

已实现：

- `Exchange.set_data(...)`。
- `Exchange.set_bars(...)`。
- `Strategy.on_bars(dt, bars)`。
- `on_data/on_bar` 兼容回调。
- 多标的同一 `dt` 下整体更新 broker 最新价。
- `Broker.submit_market_order(...)` 市价成交。
- `Broker.order_target_size/value/percent(...)`。
- `Broker.add_portfolio(name, cash)`。
- `portfolio="..."` 参数。
- `Market(...)` 特征对象。
- `markets.DEFAULT/CRYPTO/A_STOCK`。
- A 股基础规则：交易时间、交易日、整手、tick、不可做空、T+1 锁定。
- `Position.locked_size/available_size`。
- `stop_loss/take_profit` 形式的订单附带退出条件。
- `set_exit(symbol, ...)` 形式的退出条件修改。
- `add_exit_rule(symbol, ...)` 形式的函数型退出规则。

未实现或与目标设计不一致：

1. 当前交易接口返回 `bool`，目标设计返回 `Order | None`。
2. 当前退出条件按 `symbol` 绑定，目标设计按 `order_id` 作为用户句柄。
3. 当前参数名是 `stop_loss/take_profit`，目标设计是 `stop_loss_price/take_profit_price`。
4. 当前 `set_exit` 允许 callable，目标设计中函数型退出使用 `add_exit(order_id, condition=...)`。
5. 当前没有 `trailing_stop_pct/trailing_stop_amount`。
6. 当前没有 `Order` 模型、`get_order`、`get_exit`。
7. 当前 `submit_limit_order/cancel_order/submit_stop_order/submit_trailing_stop_order` 是未实现占位。
8. 当前 `Broker.__init__` 仍暴露 `portfolio_cash/portfolio_id`，目标设计不推荐。
9. 当前还导出 `SimpleMarket/CryptoMarket/ChinaAStockMarket`，目标设计只推荐 `Market` 和 `markets.*` 预设。
10. 当前 README 和 examples 仍可能出现旧参数名，需要在实现目标接口时同步更新。

## 推荐迁移顺序

### Phase 1：文档与用户心智统一

1. docs/design 只保留本系统设计稿和 README 索引。
2. README 只展示 `on_bars`、`Broker`、`Market`、`portfolio` 主路径。
3. examples 分为单标的、多标的、分仓、退出条件四类典型场景。
4. README 明确限价单尚未实现。

### Phase 2：Order 最小模型

1. 新增 `Order` 数据结构。
2. 市价单成交成功返回 `Order`。
3. 被拒绝或无交易返回 `None`。
4. 保留旧 `bool` 兼容需要谨慎处理，避免破坏测试。
5. 增加 `get_order/get_orders/get_active_order`。

### Phase 3：退出条件绑定到 Order

1. 新增 `stop_loss_price/take_profit_price` 参数。
2. 兼容旧 `stop_loss/take_profit`，但文档不再推荐。
3. `set_exit(order_id, ...)` 替代 `set_exit(symbol, ...)`。
4. `clear_exit(order_id)`。
5. `get_exit(order_id)`。
6. 函数型退出迁移为 `add_exit(order_id, condition=...)`。

### Phase 4：Trailing stop

1. 支持 `trailing_stop_pct`。
2. 支持 `trailing_stop_amount`。
3. 明确移动止损锚点更新规则。
4. 增加多头和空头测试。

### Phase 5：最小限价单

1. 实现 pending limit order。
2. `cancel_order(order_id)`。
3. 基于 bar high/low 判断触发。
4. 不做队列位置和部分成交。

### Phase 6：按真实需求扩展数据类型

只有当策略真实需要时，再实现：

1. `set_books/on_books`。
2. `set_trades/on_trades`。
3. `set_news/on_news`。
4. 多数据源固定调度顺序。

## 典型用户场景

### 单标的均线

```python
class SmaStrategy(Strategy):
    def on_init(self):
        self.symbol = "BTCUSDT"
        self.prices = []

    def on_bars(self, dt, bars):
        price = bars[self.symbol]["close"]
        self.prices.append(price)
        if len(self.prices) < 30:
            return

        ma10 = sum(self.prices[-10:]) / 10
        ma30 = sum(self.prices[-30:]) / 30
        target = 0.8 if ma10 > ma30 else 0.0
        self.broker.order_target_percent(self.symbol, target, price=price)
```

### 多标的轮动

```python
from collections import defaultdict


class RotationStrategy(Strategy):
    def on_init(self):
        self.history = defaultdict(list)

    def on_bars(self, dt, bars):
        for symbol, bar in bars.items():
            self.history[symbol].append(bar["close"])

        if not all(len(values) >= 20 for values in self.history.values()):
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

### 分仓

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001)
broker.add_portfolio("trend", cash=60_000)
broker.add_portfolio("mean_reversion", cash=20_000)


class MultiBookStrategy(Strategy):
    def on_bars(self, dt, bars):
        btc = bars["BTCUSDT"]["close"]
        eth = bars["ETHUSDT"]["close"]

        self.broker.order_target_percent("BTCUSDT", 0.8, price=btc, portfolio="trend")
        self.broker.order_target_percent("ETHUSDT", 0.5, price=eth, portfolio="mean_reversion")
```

### 订单附带止盈止损

```python
class BreakoutStrategy(Strategy):
    def on_init(self):
        self.symbol = "BTCUSDT"
        self.order = None

    def on_bars(self, dt, bars):
        price = bars[self.symbol]["close"]

        if self.order is None:
            self.order = self.broker.order_target_percent(
                self.symbol,
                0.8,
                price=price,
                stop_loss_price=price * 0.95,
                take_profit_price=price * 1.10,
            )
            return

        if self.broker.get_position_size(self.symbol) > 0:
            self.broker.set_exit(
                self.order.id,
                stop_loss_price=price * 0.98,
                take_profit_price=price * 1.12,
            )
```

### 移动止损

```python
order = self.broker.order_target_percent(
    "BTCUSDT",
    0.8,
    price=price,
    trailing_stop_pct=0.05,
)
```

### 函数型退出

```python
def below_ma_exit(ctx):
    ma = ctx.state["ma"]
    return ctx.position.size > 0 and ctx.price < ma[-1]


order = self.broker.order_target_percent("BTCUSDT", 0.8, price=price)
self.broker.add_exit(order.id, name="below_ma", condition=below_ma_exit, state={"ma": self.ma})
```

## 明确不进入当前 MVP

- 初始持仓参数。
- 多批次持仓独立止盈止损。
- 部分成交。
- 订单簿队列位置。
- 通用事件系统。
- 自动缺失数据补齐。
- 多数据源复杂同步。
- per-symbol 市场规则。
- 入场 stop order。
- 完整交易所风控模拟。

这些能力只有在真实场景反复出现后再设计。
