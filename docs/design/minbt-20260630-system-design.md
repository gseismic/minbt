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
import pandas as pd
from minbt import Broker, Exchange, Strategy


class MyStrategy(Strategy):
    def on_init(self):
        self.symbol = "BTCUSDT"

    def on_bars(self, dt, bars):
        price = bars[self.symbol]["close"]
        self.broker.order_target_percent(self.symbol, 0.8, price=price)


data = pd.DataFrame([
    {"dt": "2026-01-01", "symbol": "BTCUSDT", "close": 100.0},
    {"dt": "2026-01-02", "symbol": "BTCUSDT", "close": 105.0},
])

broker = Broker(initial_cash=100_000, fee_rate=0.001)
strategy = MyStrategy(strategy_id="demo", broker=broker)

exchange = Exchange()
exchange.set_bars(data)
exchange.add_strategy(strategy)
exchange.run()
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
|`on_xx(dt, data)`|当前时间截面的同类数据|
|`Broker`|唯一交易入口|
|`Order`|用户提交的一笔交易意图及其句柄|
|`portfolio`|分仓名称|
|`Market`|市场特征配置|

`logger` 不进入入门概念。日志只用于诊断，不属于 minbt 核心策略接口。

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

### 日志接口

日志设计保持最小：

- 直接使用 `loguru.logger`，不再封装 `I18nLogger`。
- 不提供 `configure_logging()` / `disable_logging()` 等二次配置接口。
- minbt 导入时执行 `logger.disable("minbt")`，默认关闭库内部日志。
- 用户需要诊断时调用 `logger.enable("minbt")`。
- 用户需要文件、屏幕、轮转、保留等能力时，直接使用 loguru 原生 `logger.add(...)`。

示例：

```python
from minbt import logger

logger.enable("minbt")
logger.add("logs/minbt.log", level="INFO")
```

如果用户脚本完全拥有当前进程的 loguru 配置，可以使用：

```python
from minbt import logger

logger.remove()
logger.add("logs/minbt.log", level="INFO")
logger.enable("minbt")
```

约束：

- `logger.remove()` 会影响进程级 loguru sink，只应由应用入口调用。
- examples 不应自定义 `QuietLogger`。
- `Broker`、`Exchange`、`Strategy` 的 `logger=None` 是调试/测试注入参数，不属于入门主路径。
- 自定义 logger 注入只要求提供用到的方法：`debug(...)`、`info(...)`、`warning(...)`、`error(...)`。

### 内部接口

内部接口面向系统模块，目标是正确性、可维护性和可测试性。

内部接口包括：

- `Market.validate_order(...)`
- `Market.on_new_dt(...)`
- `Market.on_order_filled(...)`
- `Broker.on_new_price(...)`
- `Broker.process_pending_orders(...)`
- `Broker.check_exit_rules(...)`
- `Strategy.set_exchange(...)`
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
7. 用户接口只使用 `portfolio`，不暴露 `portfolio_id`。

## 数据接入与策略回调

### 目标原则

目标设计一次性定义常见回测数据类型，不把 `on_data/on_bar` 作为用户接口。

所有数据回调遵循同一个规则：

> `on_xx(self, dt, data)` 表示在同一个回测时间 `dt`，收到某一类数据的完整时间切片。

单标的是多标的的特例。用户接口不提供单标的专用结构，不引入 `tick.price()` 这类包装对象。

### Exchange 用户接口

```python
exchange = Exchange()

exchange.set_bars(
    data,
    *,
    date_key: str = "dt",
    symbol_key: str = "symbol",
    price_key: str = "close",
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
    price_key: str = "price",
) -> None

exchange.set_news(
    data,
    *,
    date_key: str = "dt",
) -> None

exchange.add_strategy(strategy: Strategy) -> None
exchange.run() -> None
```

参数语义：

|参数|说明|
|---|---|
|`data`|列表、pandas DataFrame 或 polars DataFrame|
|`date_key`|回测时间字段，必须存在|
|`symbol_key`|标的字段，bars、books、trades 必须存在|
|`price_key`|用于更新 broker 最新价的字段|

设计约束：

- 目标用户接口不支持 `date_key=None`。
- 单标的数据也必须提供 `date_key` 和 `symbol_key`。
- `set_data(...)` 不进入目标用户接口。
- Exchange 可以只注册部分数据源。
- 未注册的数据源不会触发对应回调。
- 某个 `dt` 下某类数据为空时，不调用对应 `on_xx`。

策略管理：

- `add_strategy(strategy)` 是主路径用户接口；没有策略时，Exchange 没有可执行对象。
- `remove_strategy(strategy_id)` 是高级管理接口，用于复用同一个 Exchange 时移除策略，不属于入门主路径。
- `reset_market_state()` 是运行时内部/测试辅助接口，不作为推荐用户接口。

### 数据切片结构

bars：

```python
def on_bars(self, dt, bars: dict[str, Bar]) -> None:
    ...
```

`Bar` 至少包含：

```python
{
    "dt": ...,
    "symbol": "BTCUSDT",
    "close": 100.0,
}
```

可选包含：

```python
{
    "open": 99.0,
    "high": 101.0,
    "low": 98.0,
    "volume": 123.4,
}
```

books：

```python
def on_books(self, dt, books: dict[str, Book]) -> None:
    ...
```

推荐 `Book` 结构：

```python
{
    "dt": ...,
    "symbol": "BTCUSDT",
    "bids": [(100.0, 1.2), (99.9, 2.0)],
    "asks": [(100.1, 0.8), (100.2, 1.5)],
}
```

trades：

```python
def on_trades(self, dt, trades: dict[str, list[TradeRecord]]) -> None:
    ...
```

推荐 `TradeRecord` 结构：

```python
{
    "dt": ...,
    "symbol": "BTCUSDT",
    "price": 100.0,
    "qty": 0.1,
    "side": "buy",
}
```

news：

```python
def on_news(self, dt, news: list[NewsItem]) -> None:
    ...
```

推荐 `NewsItem` 结构：

```python
{
    "dt": ...,
    "title": "...",
    "symbols": ["BTCUSDT"],
    "sentiment": 0.4,
}
```

### 数据分组规则

bars：

- 同一 `(dt, symbol)` 只能有一条。
- 回调参数是 `dict[str, Bar]`。
- `price_key` 默认是 `close`。
- Exchange 在 `on_bars` 前用每个 symbol 的 `bar[price_key]` 更新 broker 最新价。

books：

- 同一 `(dt, symbol)` 只能有一个盘口快照。
- 回调参数是 `dict[str, Book]`。
- `price_key=None` 时不更新 broker 最新价。
- 如果传入 `price_key`，Exchange 在 `on_books` 前用 `book[price_key]` 更新 broker 最新价。
- 如果策略要用 mid price，可在策略中计算并显式把 price 传给 broker。

trades：

- 同一 `(dt, symbol)` 可以有多条交易明细。
- 回调参数是 `dict[str, list[TradeRecord]]`。
- `price_key` 默认是 `price`。
- Exchange 在 `on_trades` 前使用该 `dt` 下每个 symbol 最后一条 trade 的 `price_key` 更新 broker 最新价。

news：

- 同一 `dt` 可以有多条新闻。
- 回调参数是 `list[NewsItem]`。
- news 默认不更新 broker 最新价。
- news 可以通过 `symbols` 关联标的，但不强制按 symbol 分组。

### Strategy 用户接口

```python
class Strategy:
    def __init__(
        self,
        strategy_id: str,
        broker: Broker | None = None,
        params: dict | None = None,
        logger=None,
    ) -> None:
        ...

    def on_init(self) -> None:
        pass

    def on_bars(self, dt, bars: dict[str, Bar]) -> None:
        pass

    def on_books(self, dt, books: dict[str, Book]) -> None:
        pass

    def on_trades(self, dt, trades: dict[str, list[TradeRecord]]) -> None:
        pass

    def on_news(self, dt, news: list[NewsItem]) -> None:
        pass

    def on_finish(self) -> None:
        pass
```

用户可以只实现需要的回调。未实现的回调按空操作处理。

构造语义：

- `strategy_id` 是策略实例名称，用于 Exchange 管理策略。
- `broker` 是策略交易入口；主路径推荐构造时传入。
- `params` 用于传入策略参数，默认空字典。
- `logger` 是调试/高级参数，不属于入门主路径。

辅助接口：

- `get_hist_equity()` 返回回测过程中记录的总权益序列。
- `get_hist_position_sizes(symbol)` 返回指定标的持仓数量序列。
- `get_broker_stats(portfolio="main")` 返回指定 portfolio 的当前权益、现金和持仓。
- `set_params(...)`、`update_params(...)` 是参数管理辅助接口。
- `set_broker(...)`、`set_exchange(...)` 是装配/运行时接口，普通用户不应在策略逻辑中手动调用。

不进入目标设计：

- 删除旧的行级/截面级兼容回调。
- 不设计 `on_tick`。
- 不设计通用 `on_event`。

## 回测时钟与执行顺序

目标调度顺序固定为：

```text
on_bars -> on_books -> on_trades -> on_news
```

同一个 `dt` 下，Exchange 按以下流程执行：

1. Exchange 进入下一个 `dt`。
2. Exchange 收集该 `dt` 下所有已注册数据源的数据切片。
3. 对所有配置了 `price_key` 的数据源，按调度顺序更新 broker 最新价。
4. Broker 基于该 `dt` 的完整可见价格检查 pending order 和退出条件。
5. Strategy 按固定顺序收到对应 `on_xx(dt, data)` 回调。
6. 同一 `dt` 的所有回调结束后，记录权益和持仓历史。

关键约束：

- 多标的策略在任意 `on_xx` 中都必须看到该数据类型的完整时间截面。
- 同一 `dt` 只有一次 pending order 和退出条件检查，避免一个时间点内多次隐式交易。
- 如果同一 `dt` 下多个数据源都提供同一 symbol 的价格，后调度的数据源覆盖先调度的数据源。
- 策略回调看到的是该 `dt` 完整价格更新和退出处理后的账户状态。

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

不进入目标用户接口：

- `portfolio_cash`
- `portfolio_id`
- `initial_positions`

原因：

- `portfolio_cash` 会引入总现金、主组合现金和未分配现金三套概念。
- `portfolio_id` 是内部标识命名，不应进入用户接口。
- `initial_positions` 会引入成本价、杠杆、保证金、可用数量和锁定批次的复杂初始化语义。

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
- 所有 portfolio 共享同一个 broker 的订单系统、fee、杠杆配置。
- market 规则由 broker 按 symbol 路由；portfolio 不决定市场规则。

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

## Market 市场特征

### 推荐写法

默认市场：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001)
```

使用预设：

```python
from minbt import Broker, markets

broker = Broker(initial_cash=100_000, fee_rate=0.0005, market=markets.CRYPTO)
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH", "510300.SH"])
```

语义：

- `market` 是默认市场规则。
- 未显式映射的 symbol 使用默认市场规则。
- `add_market(name, market, symbols)` 在配置期把一组 symbol 路由到指定市场规则。
- `add_market(...)` 应在回测运行和任何交易发生前调用。
- 一个 symbol 同一时间只能属于一个 market。
- `get_market(symbol)` 返回该 symbol 当前市场规则的快照，供调试和测试使用。

跨市场示例：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.0005, market=markets.CRYPTO)
broker.add_portfolio("ashare", cash=60_000)
broker.add_portfolio("crypto", cash=40_000)
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])

self.broker.order_target_percent("600519.SH", 0.8, price=a_price, portfolio="ashare")
self.broker.order_target_percent("BTCUSDT", 0.8, price=btc_price, portfolio="crypto")
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

目标用户接口不提供 `SimpleMarket()`、`CryptoMarket()`、`ChinaAStockMarket()` 这类市场工厂。

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
    portfolio: str
    order_type: Literal["market", "limit"]
    source: Literal[
        "submit_market_order",
        "submit_limit_order",
        "target_size",
        "target_value",
        "target_percent",
        "close_position",
        "close_portfolio",
        "cancel_order",
    ]
    side: Literal["buy", "sell", "none"]
    qty: float
    status: Literal["pending", "filled", "canceled", "rejected", "skipped"]
    requested_price: float | None
    limit_price: float | None
    filled_qty: float
    avg_price: float | None
    reason: str | None
    created_dt: Any | None
    updated_dt: Any | None
```

字段语义：

|字段|说明|
|---|---|
|`id`|用户侧订单句柄|
|`symbol`|交易标的|
|`portfolio`|分仓名称|
|`order_type`|订单类型|
|`source`|产生订单的用户接口|
|`side`|买、卖或无交易|
|`qty`|本次订单增量数量，目标不变时为 `0`|
|`status`|当前订单状态|
|`requested_price`|用户传入的参考价格或市价成交参考价|
|`limit_price`|限价单价格，非限价单为 `None`|
|`filled_qty`|已成交数量|
|`avg_price`|成交均价|
|`reason`|`rejected` 或 `skipped` 的原因|
|`created_dt`|创建时间|
|`updated_dt`|最近更新时间|

状态语义：

|状态|说明|
|---|---|
|`pending`|限价单已接受但尚未成交|
|`filled`|订单已成交|
|`canceled`|pending 订单已取消|
|`rejected`|订单未被接受，例如资金不足或市场规则拒绝|
|`skipped`|合法请求但无需交易，例如目标仓位未变化|

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
) -> Order
```

语义：

- `qty > 0` 表示买入或增加多头。
- `qty < 0` 表示卖出或增加空头。
- `qty == 0` 是无效订单。
- `price=None` 时使用 broker 内部最新价。
- 显式传 `price` 时，broker 先更新最新价，再执行订单。
- 始终返回 `Order`。
- 市价单成交成功时返回 `Order(status="filled")`。
- 被市场规则拒绝或资金不足时返回 `Order(status="rejected", reason=...)`。
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
) -> Order

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
) -> Order

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
) -> Order
```

语义：

- `order_target_size` 调到目标净持仓。
- `order_target_value` 调到目标名义金额。
- `order_target_percent` 调到组合权益比例。
- 目标等于当前状态时返回 `Order(status="skipped", side="none", qty=0, reason=...)`。
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
) -> Order
```

语义：

- 表达全平该 `portfolio + symbol` 当前净持仓。
- 没有持仓时返回 `Order(status="skipped", side="none", qty=0, reason=...)`。
- 缺少价格时抛异常。
- T+1 市场可平数量不足时失败，不静默部分平仓。

关闭组合：

```python
broker.close_portfolio(portfolio: str) -> list[Order]
```

语义：

- 先检查该组合所有仓位是否都能关闭。
- 任一仓位无法关闭，则不执行任何平仓订单，返回对应 `Order(status="rejected", reason=...)`。
- 成功后平掉全部仓位，并将现金回到 `main`。
- 组合为空时返回一个 `Order(status="skipped", side="none", qty=0, reason=...)`。
- 返回值始终是 `list[Order]`，避免引入额外用户结果类型。
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

组合规则：

|组合|是否允许|行为|
|---|---|---|
|`stop_loss_price` + `take_profit_price`|允许|固定止损和固定止盈同时生效|
|`stop_loss_price` + `trailing_stop_pct`|允许|任一条件触发即退出|
|`stop_loss_price` + `trailing_stop_amount`|允许|任一条件触发即退出|
|`take_profit_price` + `trailing_stop_pct`|允许|任一条件触发即退出|
|`take_profit_price` + `trailing_stop_amount`|允许|任一条件触发即退出|
|`trailing_stop_pct` + `trailing_stop_amount`|不允许|抛 `ValueError`|
|四个参数都为空|允许|不设置退出条件|

数值校验：

- `stop_loss_price` 必须大于 0。
- `take_profit_price` 必须大于 0。
- `trailing_stop_pct` 必须满足 `0 < trailing_stop_pct < 1`。
- `trailing_stop_amount` 必须大于 0。
- `stop_loss_price` 和 `take_profit_price` 是价格，不是百分比。
- 函数型退出条件不放在 `stop_loss_price/take_profit_price` 中。

方向校验：

|方向|止损价格|止盈价格|
|---|---|---|
|多头|`stop_loss_price < reference_price`|`take_profit_price > reference_price`|
|空头|`stop_loss_price > reference_price`|`take_profit_price < reference_price`|

`reference_price` 定义：

- 下单时设置退出条件：使用订单成交均价 `order.avg_price`。
- pending 限价单附带退出条件：先保存配置，成交后用成交均价校验并激活。
- 中途调用 `set_exit(...)`：使用 broker 当前最新价。
- 没有可用参考价时抛异常。

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
) -> ExitConfig
```

语义：

- `order_id` 指向用户提交订单返回的 `order.id`。
- `set_exit(...)` 只更新传入且非 `None` 的标准退出项。
- 未传或传 `None` 的标准退出项表示不修改该项。
- 四个退出参数全为 `None` 时抛 `ValueError`。
- 同一次调用中 `trailing_stop_pct` 和 `trailing_stop_amount` 不能同时传入。
- 设置 `trailing_stop_pct` 会清除原有 `trailing_stop_amount`。
- 设置 `trailing_stop_amount` 会清除原有 `trailing_stop_pct`。
- 修改移动止损时，锚点从当前最新价重新开始。
- 如果需要删除全部退出条件，使用 `clear_exit(order_id)`。
- `order_id` 不存在或已失效时抛 `ValueError`。
- `order_id` 对应订单未成交或当前已无有效持仓时抛 `ValueError`。
- 成功后返回更新后的 `ExitConfig`。

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
broker.clear_exit(
    order_id: str,
    *,
    stop_loss_price: bool = True,
    take_profit_price: bool = True,
    trailing_stop: bool = True,
    custom: bool = True,
) -> ExitConfig
```

语义：

- 默认清除该订单关联的全部退出条件。
- `stop_loss_price=True` 表示清除固定止损。
- `take_profit_price=True` 表示清除固定止盈。
- `trailing_stop=True` 表示清除百分比或固定金额移动止损。
- `custom=True` 表示清除函数型退出条件。
- 四个布尔参数全为 `False` 时抛 `ValueError`。
- 清除后如果仍有退出条件，返回更新后的 `ExitConfig`。
- 清除后如果没有任何退出条件，返回 `ExitConfig(active=False)`。

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
    active: bool = False
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    trailing_stop_pct: float | None = None
    trailing_stop_amount: float | None = None
    trailing_anchor: float | None = None
    custom_rules: tuple[str, ...] = ()
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

当前代码已实现以下最小限价单接口。

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
) -> Order
```

取消：

```python
broker.cancel_order(order_id: str) -> Order
```

MVP 限价单规则：

- 提交成功后返回 `Order(status="pending")`。
- 资金不足或市场规则拒绝时返回 `Order(status="rejected", reason=...)`。
- 提交时按 `limit_price` 和当前账户状态预检资金，但不为 pending 订单预留资金。
- 触发时再次执行账户校验；期间资金被占用时返回 `Order(status="rejected", reason=...)`，不成交。
- `cancel_order(...)` 取消 pending 订单时，原订单更新为 canceled，并返回 `source="cancel_order"` 的取消动作 Order。
- 取消已成交、已取消或已拒绝订单时返回订单当前状态，不产生新订单。
- 每个新 bar 后，broker 只用当前最新价判断是否满足限价。
- bars 数据下当前最新价默认是 `close`，不使用 `high/low` 推断同一根 bar 内路径。
- 成交价格默认使用 `limit_price`。
- 成交仍必须通过 `Market.validate_order(...)`。
- 不模拟队列位置。
- 不模拟部分成交。
- 不做逐笔成交路径。
- 限价单成交后才激活其退出条件。
- pending 期间持仓方向变化导致附加退出条件失效时，整笔限价单 rejected，不先成交再抛异常。

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
broker.get_portfolios() -> list[str]
```

语义：

- 不传 `portfolio` 默认查询 `main`。
- `get_total_equity()` 汇总所有 portfolio。
- `get_portfolios()` 返回当前 broker 下的 portfolio 名称。
- `include_locked=True` 表示现金查询包含锁定现金。

辅助/兼容查询：

- `get_portfolio_initial_cash(portfolio=None)` 返回指定 portfolio 初始现金，主要用于分析和测试。
- `get_market_price(...)` 是 `get_last_price(...)` 的兼容别名，不推荐在新示例中使用。
- `get_all_portfolio_equity()` 是 `get_total_equity()` 的实现别名，不推荐在新示例中使用。

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

内部运行时接口：

```python
Broker.on_new_price(symbol, price, dt=None) -> None
Broker.process_pending_orders(dt=None) -> None
Broker.check_exit_rules(dt=None, data=None) -> None
```

这些接口由 Exchange 在推进回测时钟时调用。普通策略用户应通过 `Exchange.set_xx(...)` 接入数据，不应在 `on_bars` 等策略回调中手动推进 broker 价格或重复触发退出检查。

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
Market.validate_order(broker, symbol, qty, price, dt=None, portfolio="main") -> OrderValidation
Market.normalize_order_qty(broker, symbol, qty, price=None, portfolio="main") -> float
Market.on_new_dt(broker, dt) -> None
Market.on_order_filled(broker, symbol, qty, price, dt=None, portfolio="main", old_size=0.0) -> None
```

`old_size` 表示本次成交前的净持仓，用于 T+1 市场计算本次新开仓部分。没有该参数时，反手或加仓场景会把旧持仓错误地当作当日新开仓。

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

### 下单类接口统一返回 Order

这些用户交易接口始终返回 `Order`：

- `submit_market_order`
- `submit_limit_order`
- `order_target_size`
- `order_target_value`
- `order_target_percent`
- `close_position`
- `cancel_order`

业务结果写入 `Order.status`：

|场景|返回|
|---|---|
|市价单成交|`Order(status="filled")`|
|限价单挂起|`Order(status="pending")`|
|限价单取消|`Order(status="canceled")`|
|目标仓位无变化|`Order(status="skipped", qty=0, reason=...)`|
|空仓平仓|`Order(status="skipped", qty=0, reason=...)`|
|市场规则拒绝|`Order(status="rejected", reason=...)`|
|资金不足|`Order(status="rejected", reason=...)`|

这样用户不需要记住哪些下单类接口可能返回 `None`。稳定程序判断应依赖 `status`、`qty`、`filled_qty` 等结构化字段；`reason` 是面向人阅读的说明文本，不承诺精确字符串。

### 批量接口复用 Order

`close_portfolio(...)` 返回 `list[Order]`：

- 成功关闭时返回每个平仓订单。
- 组合为空时返回一个 `Order(status="skipped", reason=...)`。
- 无法原子关闭全部持仓时返回一个或多个 `Order(status="rejected", reason=...)`。
- 不新增专用结果类型，避免用户接口概念扩散。

### 抛异常

以下属于编程错误，应抛异常：

- `price <= 0`。
- 普通市价单或限价单 `qty == 0`。
- `portfolio` 不存在。
- `order_id` 不存在。
- `stop_loss_price/take_profit_price` 非正。
- `trailing_stop_pct/trailing_stop_amount` 非正。
- 同时设置 `trailing_stop_pct` 和 `trailing_stop_amount`。
- `date_key` 缺失。
- `symbol_key` 缺失。
- 多标的数据未提供 `date_key`。
- 同一 `(dt, symbol)` 重复。

## 当前代码现状

截至 2026-06-30，本文定义的 MVP 主路径已经实现：

1. Exchange 提供 `set_bars/set_books/set_trades/set_news`，要求显式时间字段，并按固定顺序调度完整时间切片。
2. Strategy 用户回调收敛为 `on_init/on_bars/on_books/on_trades/on_news/on_finish`，交易统一通过 `self.broker`。
3. Broker 构造、分仓、交易和查询接口使用 `portfolio`，不暴露旧的账户初始化与内部控制参数。
4. 市价单、目标仓位、平仓和限价单统一返回 Order，业务失败写入 status 和 reason。
5. 标准退出、追踪止损和函数型退出按当前持仓生命周期内有效的 order ID 管理。
6. `close_portfolio()` 在成交前完成市场与账户顺序预检，避免部分关闭。
7. Market 特征和预设支持交易时间、整手、tick、不可做空和 T+1；跨零反手也必须满足可平数量。
8. README、编号示例和 usage skill 使用本文定义的目标接口。

当前仍明确不进入 MVP 的能力见文末“明确不进入当前 MVP”。后续扩展必须先更新设计，不恢复已删除的兼容入口。

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
- per-symbol 手续费、默认杠杆和保证金模型。
- 入场 stop order。
- 完整交易所风控模拟。

这些能力只有在真实场景反复出现后再设计。
