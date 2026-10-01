# minbt

minbt 是一个最简回测框架。目标不是模拟完整交易所，而是让用户用少量代码完成：

1. 准备历史数据。
2. 实现 `Strategy` 回调。
3. 在策略里调用 `self.broker` 交易。
4. 查看现金、持仓、订单和权益结果。

当前主路径是多标的 K 线或类似 Bar 数据：已有数据用 `Exchange.set_bars(data)`，需要自动下载和缓存时用 `Exchange.add_feed(feed)`，策略通常写 `Strategy.on_bars(dt, bars)` 并通过 `Broker` 下单。

## 特性

- 支持 pandas、polars 和 `list[dict]` 数据输入。
- 支持 Binance futures K 线自动下载、SQLite 缓存和复用。
- 支持多标的同一时间截面回调：`on_bars(dt, bars)`。
- 支持自定义 Bar 回调：`on_bar(dt, bar)`。
- 支持市价单、限价单、撤单和订单状态。
- 支持目标持仓、目标名义金额、目标权重调仓。
- 支持多空双向、动态杠杆、全仓和逐仓保证金。
- 支持多 portfolio 分仓。
- 支持订单级止损、止盈、追踪止损和函数式退出条件。
- 支持市场特征配置和按 symbol 路由：默认 T+0、加密资产、A 股 T+1 预设。
- 自动记录策略权益和持仓历史。

## 安装

minbt 使用 `pyproject.toml` 管理安装配置，不再使用 `setup.py`。

从源码目录开发安装：

```bash
pip install -e .
```

核心依赖：

```text
numpy
pandas
polars
loguru
```

可选依赖：

```bash
pip install -e ".[pyta]"
pip install -e ".[plot]"
pip install -e ".[dev]"
```

`pyta2` 用于更高效的内部历史向量存储；未安装时会自动回退为 Python list。公开历史查询始终返回 Python list。`plot` 额外依赖只在绘图时需要。`dev` 包含运行测试需要的 pytest。

所有示例运行后都会保存图表，并在桌面交互环境中弹出窗口；关闭窗口后程序继续退出。自动化或无窗口运行可设置 `MINBT_EXAMPLE_SHOW=0`，只保存截图。

测试配置也放在 `pyproject.toml` 的 `[tool.pytest.ini_options]` 中，因此不需要单独维护 `pytest.ini`。

## 日志

minbt 默认关闭库内部日志，入门示例不会输出下单过程、调度过程等调试信息。

需要诊断时，直接使用 loguru：

```python
from minbt import logger

logger.enable("minbt")          # 输出 minbt 内部日志到当前 loguru sink，默认是 stderr
logger.add("logs/minbt.log")    # 也可以增加文件输出
```

如果脚本由你完全控制，并且只希望写文件、不希望输出到屏幕，可以按 loguru 原生方式配置：

```python
from minbt import logger

logger.remove()
logger.add("logs/minbt.log", level="INFO")
logger.enable("minbt")
```

`logger.remove()` 会影响当前进程的全局 loguru sink；如果你的应用已经有日志系统，不要在库代码或共享模块里调用它。

## 快速开始

下面是一个完整可运行的最小回测：

```python
import pandas as pd

from minbt import Broker, Exchange, Strategy


class DemoStrategy(Strategy):
    def on_init(self):
        self.step = 0
        self.symbol = "BTCUSDT"

    def on_bars(self, dt, bars):
        price = bars[self.symbol]["close"]

        if self.step == 0:
            self.broker.order_target_percent(self.symbol, 0.8, price=price)
        elif self.step == 2:
            self.broker.close_position(self.symbol, price=price)

        self.step += 1

    def on_finish(self):
        print("equity:", self.broker.get_total_equity())
        print("position:", self.broker.get_position_size(self.symbol))


data = pd.DataFrame(
    [
        {"dt": "2026-01-01", "symbol": "BTCUSDT", "close": 100.0},
        {"dt": "2026-01-02", "symbol": "BTCUSDT", "close": 110.0},
        {"dt": "2026-01-03", "symbol": "BTCUSDT", "close": 120.0},
    ]
)

broker = Broker(initial_cash=10_000, fee_rate=0.001)
strategy = DemoStrategy(strategy_id="demo", broker=broker)

exchange = Exchange()
exchange.set_bars(data)
exchange.add_strategy(strategy)
exchange.run()
```

这个例子展示了 minbt 的稳定用户模型：

- `Exchange` 负责喂数据和推进时间。
- `Strategy` 负责读当前时间截面的数据并产生交易意图。
- `Broker` 是唯一交易入口。
- `Order` 是下单返回的结果和退出条件句柄。

## 策略开发流程

推荐按下面步骤写策略：

1. 准备包含 `dt`、`symbol`、`close` 的历史数据。
2. 继承 `Strategy`，在 `on_init()` 初始化状态。
3. 在 `on_bars(dt, bars)` 读取当前时间截面数据。
4. 用 `self.broker.order_target_percent(...)` 或其他 broker 接口表达交易意图。
5. 在 `on_finish()` 或回测结束后查询结果。

最常用模板：

```python
class MyStrategy(Strategy):
    def on_init(self):
        self.symbol = "BTCUSDT"
        self.prices = []

    def on_bars(self, dt, bars):
        price = bars[self.symbol]["close"]
        self.prices.append(price)

        if len(self.prices) < 20:
            return

        ma = sum(self.prices[-20:]) / 20
        target = 0.8 if price > ma else 0.0
        self.broker.order_target_percent(self.symbol, target, price=price)
```

单标的是多标的的特例。即使只有一个标的，`bars` 仍然是 `{symbol: row}`：

```python
price = bars["BTCUSDT"]["close"]
```

多标的策略直接遍历同一时间截面：

```python
def on_bars(self, dt, bars):
    returns = {}
    for symbol, row in bars.items():
        self.history.setdefault(symbol, []).append(row["close"])
        prices = self.history[symbol]
        if len(prices) >= 20:
            returns[symbol] = prices[-1] / prices[-20] - 1

    if not returns:
        return

    selected = max(returns, key=returns.get)
    for symbol, row in bars.items():
        target = 0.8 if symbol == selected else 0.0
        self.broker.order_target_percent(symbol, target, price=row["close"])
```

## 数据约定

`set_bars()` 只负责把行数据转换为 `Bar(kind="kline")`，不负责决定哪一个字段用于盈亏：

```python
exchange.set_bars(data, date_key="dt", symbol_key="symbol")
```

`data` 支持：

- `pandas.DataFrame`
- `polars.DataFrame`
- `list[dict]`

所有 Bar 入口必需字段：

- `dt`: 回测时间，字段名可用 `date_key` 改。
- `symbol`: 标的代码，字段名可用 `symbol_key` 改。

Kline 不强制完整 OHLCV。`close` 只是常见字段；如果用户只需要 `value`、`signal` 或其他字段，
也可以直接放入 Bar 的 `data`。

关键规则：

- Kline 和完整 OrderBook 在同一来源同一 `(dt, symbol)` 只能有一条 Bar；Trade 和自定义 Bar 可以有多条。
- Exchange 会按时间排序并在每个 `dt` 聚合完整截面。
- 策略回调收到的 `dt` 会统一为 UTC `datetime.datetime`。
- 数字时间戳按数量级推断秒、毫秒、微秒或纳秒；有歧义时先用
  `minbt.data.model.normalize_datetime(value, unit="ms")` 显式转换，再传入数据。
- 同一 `dt` 下，Exchange 先收齐全部市场事件；Broker 按 `mark_price` 选择估值价格，
  批量更新所有标的，再处理限价单和退出条件，最后调用策略回调。
- 不提供 `date_key=None` 或行号时间；时间字段必须显式存在。

## 通用 Bar 和其他市场数据

Kline、OrderBook、Trade、Price 都是 Bar 的不同 `kind`，不要求共享一套字段：

```python
from minbt import Bar

Bar(dt, "BTCUSDT", "price", {"value": 100.2, "source": "exchange_mark"})
Bar(dt, "BTCUSDT", "orderbook", {"bids": [(100.0, 1.0)], "asks": [(100.1, 1.0)]})
Bar(dt, "BTCUSDT", "trade", {"price": 100.05, "qty": 0.2, "side": "buy"})
```

`News` 是独立的时间事件，不默认参与盈亏。CSV、iosql 是具体 Feed 的读取来源，不需要用户创建
Storage、Schema 或 Adapter。

通用 Bar 存储使用最小字段信封：

```text
dt,symbol,kind,data
```

CSV 中 `data` 是 JSON 文本；iosql 中 `dt` 是 UTC 毫秒时间戳、`data` 是 JSON 文本。读取通用
Bar 时使用 `CsvBarFeed` 或 `IosqlBarFeed`，它们不会解释 `kind` 的字段。

## 自动下载加密货币 K 线

如果你不想先手工准备 CSV，可以直接接入 Binance futures 历史 K 线：

```python
from minbt import Exchange
from minbt.data import binance

exchange = Exchange()
exchange.add_feed(
    binance.BinanceKlineFeed(
        symbols=["BTCUSDT", "ETHUSDT"],
        interval="1h",
        start="2024-01-01",
        end="2024-01-03",
        cache_dir="./data",
    )
)
```

第一次运行会自动下载并写入 `{cache_dir}/minbt-data.sqlite3`，后续相同区间会复用本地缓存。策略仍然只写 `on_bars(dt, bars)`：

```python
def on_bars(self, dt, bars):
    price = bars["BTCUSDT"]["close"]
    self.broker.order_target_percent("BTCUSDT", 0.8, price=price)
```

完整示例见 `examples/300_feed_crypto_binance.py`。

默认 `closed_only=True`，只回放准备时已确认收盘的 K 线；缓存无法证明 K 线是在收盘后抓取时会重新下载，
离线模式下则报告缓存不完整。设为 `closed_only=False` 可包含尚未收盘的 K 线。

## CSV / iosql K 线回放

对于 `crypto.bn_data_sync` 生成的月度 CSV 或 iosql 库，可以使用 Kline 专用历史 Feed。
有序 Feed 支持渐进回放，Exchange 只保留当前时间批次和各来源的少量读取缓冲：

```python
from minbt.data import BinanceKlineCsvFeed, BinanceKlineIosqlFeed

exchange.add_feed(BinanceKlineCsvFeed(
    root="/media/lsl/Z1/findata/crypto/binance/future_usdt/kline.csv/1m",
    symbols=["BTCUSDT"],
    interval="1m",
    start="2023-01-01",
    end="2023-01-03",
))

# 或使用 iosql：
exchange.add_feed(BinanceKlineIosqlFeed(
    uri="sqlite:///media/lsl/Z1/findata/crypto/binance/future_usdt/kline.csv.iosql",
    interval="1m",
    symbols=["BTCUSDT"],
    start="2023-01-01",
    end="2023-01-03",
    batch_size=10_000,
))

exchange.run()  # auto：有序来源优先使用渐进回放
exchange.run(load_mode="preload")
exchange.run(load_mode="incremental")
```

iosql 读取依赖 `query(..., order_by="open_time").iter_rows(...)` 的有序查询，
需要安装 iosql v0.3.x 或更新版本。`start/end` 在 minbt 中是半开区间 `[start, end)`；
iosql 的闭区间会由 Feed 自动转换。完整示例见 `examples/301_feed_csv.py` 和
`examples/302_feed_iosql.py`。

两个 Feed 默认进行数据完整性预检：显式请求的 symbol 必须在指定区间内有数据；
CSV 请求月份不能缺文件；iosql 的 interval/table 必须存在且表契约可查询。检查失败会
在策略开始前抛出带参数上下文的异常，不会静默完成空回测。

渐进回放用额外的迭代与归并开销换取更低的历史行情内存；全量预加载适合小数据和速度优先的
场景。具体速度和内存取决于来源、时间批次大小和数据字段。

如果存储的是 OrderBook、Trade、Price 或自定义 Bar，使用通用信封：

```python
from minbt.data import CsvBarFeed

exchange.add_feed(CsvBarFeed("/path/to/bars.csv"))
```

通用 CSV/iosql Feed 只要求 `dt`、`symbol`、`kind`、`data`，不会把数据强制解释成 OHLCV。

`price` 或其他自定义 kind 会通过 `on_bar(dt, bar)` 回调给策略。`on_bar` 按事件逐条调用；同一
`dt` 下的多个自定义 Bar 不会合并成 `symbol -> data` 的截面。

除 bars 外，Exchange 还支持相同时间截面模型的数据入口：

- `set_books(data, date_key="dt", symbol_key="symbol")`
- `set_trades(data, date_key="dt", symbol_key="symbol")`
- `set_news(data, date_key="dt", symbol_key="symbol")`

回调顺序固定为：

```text
on_bars -> on_books -> on_trades -> on_bar -> on_news
```

Feed 注册时可以指定 `feed_priority`。它只决定同一时间点的分发顺序，不决定 Broker 的估值
价格；同优先级来源在同一时间、同一数据族、同一 symbol 真正重叠时会 Warning。

例如使用交易所 mark price 计算盈亏：

```python
broker = Broker(
    initial_cash=10_000,
    mark_price="price.value",
)
```

普通 Kline 回测不需要配置 `mark_price`，`Broker()` 默认使用 `kline.close`。推荐使用字符串形式，
例如 `mark_price="orderbook.mid"` 或 `mark_price="trade.price"`。`(kind, field)` 元组、
`(feed_name, kind, field)` 三元组和 callable 属于高级用法；三元组会把 Broker 配置耦合到 Feed 名称，
Feed 重命名后需要同步修改，只有在需要精确路由时使用。`mark_price=None` 表示关闭自动估值。
同一批次出现多个候选价格时默认报错；需要明确选择时再配置
`mark_price_aggregation="first"`、`"last"` 或自定义函数。
如果账户已有持仓或挂单，却从未得到可用估值价格，Broker 会报错并提示补充字段或修改 `mark_price`。

## Broker 交易接口

策略里只通过 `self.broker` 交易，不在 `Strategy` 上添加交易语法糖。

### 市价单

```python
order = self.broker.submit_market_order("BTCUSDT", qty=1, price=100)
```

- `qty > 0` 表示买入或增加多头。
- `qty < 0` 表示卖出或增加空头。
- `qty == 0` 会抛 `ValueError`。
- `price=None` 时使用 broker 当前最新价；没有最新价时抛 `ValueError`。

### 目标仓位

真实策略通常表达“把仓位调到多少”，推荐优先使用目标仓位接口：

```python
self.broker.order_target_size("BTCUSDT", target_size=2, price=100)
self.broker.order_target_value("BTCUSDT", target_value=5_000, price=100)
self.broker.order_target_percent("BTCUSDT", target_percent=0.8, price=100)
```

含义：

- `target_size`: 目标净持仓数量。
- `target_value`: 目标名义金额。
- `target_percent`: 目标 portfolio 权益比例。

目标不变时返回 `Order(status="skipped", qty=0)`，不会返回 `None`。

### 平仓

```python
self.broker.close_position("BTCUSDT", price=105)
self.broker.close_portfolio("trend")
```

- `close_position()` 全平指定标的净持仓。
- `close_portfolio()` 原子关闭指定 portfolio；任一仓位不能关闭时，不执行任何平仓。
- `close_portfolio()` 成功后同时取消该 portfolio 的 pending 限价单；预检失败时订单保持
  pending，避免出现活动订单指向已删除 portfolio。

### 订单结果

下单类接口统一返回 `Order`：

```python
order = self.broker.order_target_percent("BTCUSDT", 0.8, price=100)

if order.status == "filled":
    print(order.id, order.filled_qty, order.avg_price)
elif order.status == "rejected":
    print(order.reason)
```

常见状态：

- `filled`: 已成交。
- `pending`: 限价单挂起。
- `canceled`: 已撤销。
- `rejected`: 业务拒绝，例如资金不足或市场规则拒绝。
- `skipped`: 合法请求但无需交易。

稳定程序判断应依赖 `status`、`qty`、`filled_qty`、`avg_price` 等结构化字段；`reason` 是人读说明文本，不承诺精确字符串。

## 限价单

限价单按当前最新价触发，不根据 bar 的 `high/low` 推断同一根 bar 内路径：

```python
order = self.broker.submit_limit_order(
    "BTCUSDT",
    qty=1,
    limit_price=95,
    stop_loss_price=90,
    take_profit_price=105,
)

self.broker.cancel_order(order.id)
```

规则：

- 买入限价单在最新价小于等于 `limit_price` 时成交。
- 卖出限价单在最新价大于等于 `limit_price` 时成交。
- 提交时预检资金，但不为 pending 订单预留资金。
- 触发时再次检查资金和市场规则。
- 回放中只有当前批次更新了该标的估值价格时才会尝试触发；其他标的或其他事件不会用旧价格触发挂单。
- 不模拟队列位置和部分成交。

## 止盈止损和退出条件

真实交易中，止盈止损通常随订单提交，持仓期间可以修改。

### 提交订单时设置

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

参数：

- `stop_loss_price`: 固定止损触发价。
- `take_profit_price`: 固定止盈触发价。
- `trailing_stop_pct`: 百分比追踪止损。
- `trailing_stop_amount`: 固定金额追踪止损。

`trailing_stop_pct` 和 `trailing_stop_amount` 互斥；固定止损/止盈可以和追踪止损同时存在。
同一净持仓生命周期内，同方向成交只更新传入的退出字段，未传字段沿用已有配置；调用 `clear_exit()` 可显式清除条件。

### 持仓中修改

```python
self.broker.set_exit(
    order.id,
    stop_loss_price=price * 0.98,
    take_profit_price=price * 1.12,
)
```

清除退出条件：

```python
self.broker.clear_exit(order.id, trailing_stop=True)
```

### 函数式退出

复杂退出逻辑使用 `add_exit()`，本质是“退出条件”，不强行区分止盈或止损：

```python
def exit_if_breaks_support(ctx):
    return ctx.price < ctx.state["support"]


order = self.broker.submit_market_order("BTCUSDT", qty=1, price=price)
self.broker.add_exit(
    order.id,
    name="support_break",
    condition=exit_if_breaks_support,
    state={"support": price * 0.96},
)
```

`ctx` 包含 `order_id/symbol/portfolio/dt/price/position/broker/data/state`。函数返回 `True` 时，broker 使用当前最新价市价平仓。

## Portfolio 和市场规则

默认只有 `main` portfolio：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001)
broker.add_portfolio("trend", cash=30_000)

broker.order_target_percent("BTCUSDT", 0.8, price=100, portfolio="trend")
```

常用查询：

```python
broker.get_total_equity()
broker.get_equity(portfolio="main")
broker.get_cash(portfolio="main")
broker.get_position("BTCUSDT", portfolio="main")
broker.get_position_size("BTCUSDT", portfolio="main")
broker.get_position_sizes(portfolio="main")
broker.get_orders(portfolio="main", symbol="BTCUSDT")
broker.get_portfolios()
```

`get_position()` 查询不存在的标的时返回 `None`，不会创建空仓；`get_positions()` 返回新的字典快照，
其中的 `Position` 对象仍是当前持仓对象。策略应通过 Broker 的交易接口修改仓位，不要直接改写查询结果。

市场预设：

```python
from minbt import Broker, markets

broker = Broker(initial_cash=100_000, fee_rate=0.0005, market=markets.CRYPTO)
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH", "510300.SH"])
```

`market` 是默认市场规则，未通过 `add_market(...)` 显式映射的 symbol 使用默认规则。上例中 `600519.SH` 和 `510300.SH` 使用 A 股规则，`BTCUSDT` 等未映射 symbol 使用 crypto 规则。

`add_market(...)` 应在回测运行和任何交易发生前调用。查询某个 symbol 使用的市场规则时使用 `broker.get_market(symbol)`，返回的是快照，不能通过修改返回对象改变 broker 内部规则。

`Market` 默认使用 UTC 时区，`markets.A_STOCK` 使用 `Asia/Shanghai`。带时区的交易时间会转换到市场时区；无时区时间按 UTC 解释后再转换。设置 `lot_size`、`tick_size`、`min_qty` 或 `min_notional` 时必须使用有限正数。

`markets.A_STOCK` 是最小 A 股规则：交易时间、100 股一手、价格 tick、不可做空、T+1 持仓锁定。直接调用 broker 下单时需要传 `price_dt`；通过 Exchange 回测时，`dt` 会自动传入。

跨市场分仓：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.0005, market=markets.CRYPTO)
broker.add_portfolio("ashare", cash=60_000)
broker.add_portfolio("crypto", cash=40_000)
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])

self.broker.order_target_percent("600519.SH", 0.8, price=a_price, portfolio="ashare")
self.broker.order_target_percent("BTCUSDT", 0.8, price=btc_price, portfolio="crypto")
```

## 结果查询

Strategy 自动记录回测中的总权益和持仓数量：

```python
equity_curve = strategy.get_hist_equity()
btc_sizes = strategy.get_hist_position_sizes("BTCUSDT")
stats = strategy.get_broker_stats(portfolio="main")
```

如果要查看净盈亏曲线，请在回测开始前保存初始权益，再用权益减去初始权益：

```python
initial_equity = broker.get_total_equity()
exchange.run()
pnl_curve = [equity - initial_equity for equity in strategy.get_hist_equity()]
```

曲线中的正值表示盈利，负值表示亏损；持仓未平时是按最新价计算的未实现盈亏，最终平仓后还包含手续费影响。
可直接运行 `examples/000_core_pnl_sanity_check.py` 查看多头、空头和手续费的手算校验。

两个历史查询都返回 Python `list`。从未交易过的 symbol 返回与权益历史等长的全零列表；
安装 pyta2 只改变内部存储方式，不改变查询结果类型和缺失值语义。

也可以直接从 broker 查询当前状态：

```python
broker.get_total_equity()
broker.get_cash()
broker.get_position_sizes()
broker.get_orders()
```

## 示例

示例按分级编号法命名：首位是大类编号，接下来两位是类内序号，随后是类别标识和名称。类别依次为 `core`、`scenario`、`benchmark`、`feed`、`exchange`。
运行前请先按上方安装步骤安装 minbt 和 `plot` 依赖。示例会弹出图表窗口并同时保存到 `examples/screenshots/`；要只保存截图，可在命令前设置 `MINBT_EXAMPLE_SHOW=0`。

推荐按顺序阅读：

```bash
python examples/000_core_pnl_sanity_check.py
python examples/001_core_demo_mini.py
python examples/002_core_single_symbol_sma.py
python examples/003_core_multi_symbol_rotation.py
python examples/100_scenario_exit_rules.py
python examples/101_scenario_limit_order.py
python examples/102_scenario_single_breakout.py
python examples/103_scenario_multi_rotation.py
python examples/104_scenario_pairs_mean_reversion.py
python examples/105_scenario_cross_market.py
python examples/200_benchmark_100k_empty.py
python examples/300_feed_crypto_binance.py
python examples/301_feed_csv.py
python examples/302_feed_iosql.py
python examples/400_exchange_replay_modes.py
python examples/401_exchange_generic_bar_storage.py
```

示例文件：

- [examples/000_core_pnl_sanity_check.py](./examples/000_core_pnl_sanity_check.py)：可手算的多空、手续费和净盈亏曲线校验。
- [examples/001_core_demo_mini.py](./examples/001_core_demo_mini.py)：最小单标的示例。
- [examples/002_core_single_symbol_sma.py](./examples/002_core_single_symbol_sma.py)：单标的双均线趋势跟随。
- [examples/003_core_multi_symbol_rotation.py](./examples/003_core_multi_symbol_rotation.py)：多标的横截面动量轮动。
- [examples/100_scenario_exit_rules.py](./examples/100_scenario_exit_rules.py)：订单附带止盈止损和追踪止损。
- [examples/101_scenario_limit_order.py](./examples/101_scenario_limit_order.py)：限价单、成交和撤单。
- [examples/102_scenario_single_breakout.py](./examples/102_scenario_single_breakout.py)：单标的趋势突破。
- [examples/103_scenario_multi_rotation.py](./examples/103_scenario_multi_rotation.py)：多标的轮动和再平衡。
- [examples/104_scenario_pairs_mean_reversion.py](./examples/104_scenario_pairs_mean_reversion.py)：配对均值回归。
- [examples/105_scenario_cross_market.py](./examples/105_scenario_cross_market.py)：一个 Broker 内同时交易 A 股和 crypto。
- [examples/200_benchmark_100k_empty.py](./examples/200_benchmark_100k_empty.py)：10 万行空策略基准。
- [examples/300_feed_crypto_binance.py](./examples/300_feed_crypto_binance.py)：自动下载、缓存并回放 Binance futures K 线。
- [examples/301_feed_csv.py](./examples/301_feed_csv.py)：渐进读取 crypto.bn_data_sync 月度 CSV K 线。
- [examples/302_feed_iosql.py](./examples/302_feed_iosql.py)：使用 iosql 有序查询渐进回放 K 线。
- [examples/400_exchange_replay_modes.py](./examples/400_exchange_replay_modes.py)：通用 Bar、Feed 优先级和 Broker 估值来源。
- [examples/401_exchange_generic_bar_storage.py](./examples/401_exchange_generic_bar_storage.py)：通用 Bar CSV 存储和自定义 Bar 回调。
- [examples/example_utils.py](./examples/example_utils.py)：高级示例共用的目标名义金额调仓辅助函数。
- [examples/data.csv](./examples/data.csv)：单标的 BTCUSDT 示例行情。

## Codex Skill

仓库包含一个面向策略开发的本地 skill：

```text
./skills/minbt-usage
```

在支持本地 skills 的 Codex 环境中，可以使用：

```text
Use $minbt-usage to write a minbt strategy for my CSV data.
```

该 skill 面向用户策略开发：帮助 Agent 读取用户数据结构、选择合适示例、生成 `Strategy`、使用 `self.broker` 下单、设置退出条件，并给出最小验证命令。

## 测试

运行全量测试：

```bash
python -m pytest -q
```

只验证盈亏示例和 Broker 往返盈亏：

```bash
python -m pytest -q tests/test_pnl.py tests/test_examples.py
```

运行编译检查：

```bash
python -m compileall -q minbt tests examples
```

当前环境可能出现 `Polars binary is missing!` warning；只要测试未失败，就按环境依赖警告处理。

## 设计边界

minbt 当前明确不做：

- 核心回测不绑定外部数据源；需要下载和复用行情时，通过可选 `DataFeed` 接入，例如 Binance futures K 线。
- 不模拟滑点、订单簿队列位置和部分成交。
- 不根据 bar 的 `high/low` 推断 intrabar 路径。
- 不模拟完整交易所风控、撮合和真实订单生命周期。
- 不支持初始持仓复杂初始化。
- 不支持多批次持仓分别维护独立止盈止损。

当前资金模型是保证金账户模型。`Position.equity` 表示保证金加未实现盈亏，不是现货市值。

## ChangeLog

- [@2026-10-02] v0.1.0：修复逐仓风控、市场时区与交易单位校验、持仓查询副作用、挂单触发、退出条件继承和数据 Feed/缓存边界；支持显式时间戳单位。
- [@2026-06-24] v0.0.4：修复全仓保证金、总权益统计、日志参数和 Python 3.8 注解兼容问题。
- [@2024-11-16] v0.0.3 release。
