# minbt

minbt 是一个最简回测框架。目标不是模拟完整交易所，而是让用户用少量代码完成：

1. 准备历史数据。
2. 实现 `Strategy` 回调。
3. 在策略里调用 `self.broker` 交易。
4. 查看现金、持仓、订单和权益结果。

当前主路径是多标的 K 线或类似 Bar 数据：自己准备的数据用 `Exchange.set_bars(data)` 或自己的 Feed，策略通常写 `Strategy.on_bars(dt, bars)` 并通过 `Broker` 下单。也可以通过 `run(策略类, 配置, feed_factory=...)` 创建一次独立实验。默认模拟交易属于核心 `minbt.broker`，具体读取实现位于 `minbt.plugins`。

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
- 支持运行时间窗口、暂停策略回调、受控退出，以及独立的结果快照和状态元信息。
- 支持 JSON/Mapping 配置运行、自定义 Feed/Broker 注入和标准结果协议。

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
pip install -e ".[dev,plot]"  # 运行示例测试
```

`pyta2` 用于更高效的内部历史向量存储；未安装时会自动回退为 Python list。公开历史查询始终返回 Python list。运行示例需安装 `plot` 额外依赖；`dev` 包含 pytest 和发行物验证所需的 build、pip，运行示例测试时同时安装 `plot`。

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

下面是一个完整可运行的最小回测，与 [01_quickstart.py](examples/01_quickstart.py) 相同：

```python
import matplotlib.pyplot as plt

from minbt import Broker, Exchange, Strategy


class BuyAndHold(Strategy):
    def on_bars(self, dt, bars):
        self.broker.order_target_size("TEST", 1)


broker = Broker(initial_cash=1_000)
strategy = BuyAndHold("demo", broker=broker)
exchange = Exchange()
exchange.set_bars([
    {"dt": "2026-01-01", "symbol": "TEST", "close": 100},
    {"dt": "2026-01-02", "symbol": "TEST", "close": 120},
])
exchange.add_strategy(strategy)
exchange.run()
print(f"final_equity={broker.get_total_equity():.2f}")
plt.plot(strategy.get_hist_equity())
plt.show()
```

`order_target_size("TEST", 1)` 表示持有一个单位：第一条行情买入，后续目标不变时继续持有。默认使用当前 `close` 成交，手续费默认为零。价格从 100 涨到 120，输出 `final_equity=1020.00`，其中 20 是未平仓的浮动盈亏。

最小例子只需理解三个对象：

- `Exchange` 负责喂数据和推进时间。
- `Strategy` 负责读当前时间截面的数据并产生交易意图。
- `Broker` 是唯一交易入口。

## 策略类与配置运行

已有策略可以通过薄入口装配，每次调用创建新的 Exchange、Strategy 和账户。数据完全由你准备，
`feed_factory` 收到 `data` 参数字典，返回新的 Feed 列表或生成器：

```python
from minbt import Bar, run
from minbt.data import MemoryFeed


prepared_rows = [
    {"dt": "2026-01-01", "symbol": "TEST", "close": 100},
    {"dt": "2026-01-02", "symbol": "TEST", "close": 120},
]


def build_my_feeds(options):
    events = [Bar(row["dt"], row["symbol"], "kline", row) for row in prepared_rows]
    return [MemoryFeed(options["name"], events)]


result = run(BuyAndHold, {
    "strategy": {"id": "demo", "params": {}},
    "data": {"name": "prepared-data"},
    "broker": {"initial_cash": 1_000},
    "run": {"load_mode": "auto"},
}, feed_factory=build_my_feeds)
print(result.get_total_pnl().net_pnl)  # 20.0
```

第二个参数也可以是 JSON 文件路径。完整可运行示例与配置见
[18_config_run.py](examples/18_config_run.py) 和 [18_config_run.json](examples/18_config_run.json)。
手工构造仍是 `Strategy(strategy_id, broker=..., params=..., logger=...)`，`strategy_id` 必填。
配置运行省略 `strategy.id` 时使用策略类名；自定义策略构造函数需接受入口传入的
`strategy_id`、`broker`、`params` 和 `logger`。
`run` 字典接受原有 `start/end/load_mode`；实时控制用函数参数 `control=` 传入。

默认用现有 `Broker(**配置中的 broker)`，必须提供必要构造参数；特殊交易或记账模型可传
`broker_factory=`，它只收到 `broker` 字典并返回新的 `ReplayBrokerProtocol` 实现。
`broker: null` 可运行纯信号策略，对应账户查询会明确报错。入口复制配置，保持调用方参数不变；
配置文件按调用工作目录定位，数据路径由你的工厂解释，也可以显式使用绝对路径。

## 协议与插件扩展

协议集中在 `minbt.protocols`。扩展无需注册，直接导入自己的实现并传给 Exchange 或运行工厂：

| 契约 | 用途 |
| --- | --- |
| `DataFeedProtocol` | `name` 与 `events()`；默认回放产出原有 Bar/News |
| `BrokerProtocol` / `ReplayBrokerProtocol` | 原策略交易方法及默认回放的 `process_market_batch()` |
| `EngineProtocol` | 可选 `engine=适配器`，负责驱动策略、资源和结果映射 |
| `ResultProtocol` | 元信息、权益/持仓曲线、订单、初始资金与盈亏查询 |

默认返回现有 `RunResult`。外部引擎返回自己的独立 `ResultProtocol` 快照，核心不再次模拟账户。
适配器负责桥接本库策略回调和外部引擎；具体外部引擎 SDK 由使用者提供。
自定义 Broker 的可选订单和盈亏查询按标准字段冻结，无需继承内置 `Order` 或 `Pnl`。
绘图库直接读取结果曲线，缺失能力仍用 `NotImplementedError` 表示。

默认模拟交易属于核心：Broker、订单、分仓、持仓、盈亏、撮合和退出组件直接位于 `minbt.broker`。
数据模型与基础 Feed 位于 `minbt.data`，数据读取器从 `minbt.plugins.binance` 或
`minbt.plugins.storage` 导入。原数据读取转发路径已移除；协议直接从 `minbt.protocols` 导入。
自己的 Feed/Broker 可以保存在自己的项目，特殊市场行为通过协议和工厂扩展。
核心保留 Exchange 唯一回放循环，新配置入口只读取参数并调用你提供的工厂。
默认自备数据回测不会加载插件。职责和接口边界详见 [设计规范](docs/design/protocols/README.md)。

## 运行区间与控制

一个 Exchange 只启动一次 `run()`。独立实验或追加历史数据验证后续表现时，创建新的 Exchange、Strategy 和 Broker，从原起点完整重放，再评估新增区间。

在已注册数据与策略、尚未启动的 Exchange 上，可以指定 `[start, end)` 窗口：

```python
result = exchange.run(start="2026-01-01", end="2026-02-01")
print(result.meta["status"], result.meta["last_dt"])
curve = result.get_equity_curve()  # (UTC 时间, 账户权益)
```

`start/end=None` 表示不额外限制该侧，由数据自然决定边界。窗口起点是新实验的起点，不会自动恢复此前的指标或持仓。

需要控制执行时，提供返回当前期望状态的回调：

```python
from threading import Event


pause_requested = Event()
exit_requested = Event()


def control():
    if exit_requested.is_set():
        return "exit"
    return "pause" if pause_requested.is_set() else "continue"


result = exchange.run(control=control)
```

| 返回值 | 行为 |
| --- | --- |
| `continue` | 行情、账户和策略继续执行 |
| `pause` | 停止所有策略行情回调，账户、挂单、退出规则和曲线继续更新 |
| `exit` | 结束整个回测，返回截至最后完整处理时间的结果 |

控制检查在每个完整时间批次开始前进行，暂停期间照常检查。继续时不补发暂停期间的数据，指标重建或预热由业务逻辑负责。

`run()` 阻塞调用线程；需要界面或外部控制时，将它放到工作线程，控制线程只通过 `Event.set()/clear()` 更新状态。控制回调和结束通知只读账户，交易仍由策略行情回调与已有账户规则完成。

结果的 `meta` 包含 `status`、`reason`、最终 `control_state`、请求及实际时间、`step_count`、策略 ID 和控制变化记录。自然完成为 `completed`，主动退出为 `exited`；完成只说明可用数据处理完毕，不代表盈利或策略通过验证。程序异常仍抛出。

结果快照可直接查询和绘图，不受原账户后续变化影响：

```python
equity = result.get_equity_curve()
sizes = result.get_position_curve("BTCUSDT")
orders = result.get_orders()
pnl = result.get_total_pnl()
positions = result.get_position_sizes()
initial_cash = result.get_initial_cash()
```

多策略结果需要指定 `strategy_id`；共享 Broker 的策略 ID 查询同一账户，不能重复累加。退出后的曲线只覆盖已处理区间。完整示例见 [10_run_control.py](examples/10_run_control.py)。

权益曲线和总盈亏覆盖整个 Broker；持仓曲线 `get_position_curve(symbol)` 只记录 `main` 分仓。
其他分仓的最终持仓用 `result.get_position_sizes(portfolio="trend")` 查询。

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

- `dt`: 数据真实可见的回放时间，字段名可用 `date_key` 改；自备完整 K 线应使用完成时间。
- `symbol`: 非空字符串标的代码，去除首尾空白并转大写；交易、查询和市场路由使用相同规则。

Kline 不强制完整 OHLCV。`close` 只是常见字段；如果用户只需要 `value`、`signal` 或其他字段，
也可以直接放入 Bar 的 `data`。

关键规则：

- Kline 和完整 OrderBook 在同一来源同一 `(dt, symbol)` 只能有一条 Bar；Trade 和自定义 Bar 可以有多条。
- Exchange 会按时间聚合全部来源，策略截面按来源分别分发。同一 `dt` 有多个 Kline Feed 时，
  `on_bars` 会调用多次，每次只含该来源的标的；需要统一选股截面时，将标的放在同一个 Feed。
- 策略回调收到的 `dt` 会统一为 UTC `datetime.datetime`。
- `on_bars/on_books/on_trades` 的外层映射只读；Trade 序列是元组，常见行载荷容器也只读。
  策略需要本地增删时先用 `dict(...)` 或 `list(...)` 创建自己的容器。
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
iosql 的 `dt` 与显式 `dt_ms` 始终按毫秒解析，包括 epoch 附近的小数值；普通 CSV `dt`
继续允许 ISO 文本和按数量级推断的数字时间戳。

## 自动下载加密货币 K 线

如果你不想先手工准备 CSV，可以直接接入 Binance futures 历史 K 线：

```python
from minbt import Exchange
from minbt.plugins import binance

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

完整示例见 `examples/13_binance_feed.py`。

默认 `closed_only=True`，只回放准备时已确认收盘的 K 线；缓存无法证明 K 线是在收盘后抓取时会重新下载，
离线模式下则报告缓存不完整。下载和缓存都检查区间首尾及中间连续性；上市前或其他原因造成
数据缺失时会报错，不把缺失前缀登记为完整缓存。旧错误缓存可用 `refresh=True` 重新获取。
设为 `closed_only=False` 可包含尚未收盘的快照，其事件仍安排在该根 K 线的 `close_time`。

三个 Binance Kline Feed 均按 `close_time` 发布事件，载荷保留整数毫秒的 `open_time` 和 `close_time`。
例如 00:00 开始的一小时 K 线在 00:59:59.999 发布完整数据，避免混合分钟行情或 News 时提前使用最终结果。
缺少或无效的收盘时间会报错；`start/end` 按 `open_time` 筛选 `[start, end)`，Exchange 的运行窗口
则按事件的可见时间筛选。

## CSV / iosql K 线回放

对于 `crypto.bn_data_sync` 生成的月度 CSV 或 iosql 库，可以使用 Kline 专用历史 Feed。
有序 Feed 支持渐进回放，Exchange 只保留当前时间批次和各来源的少量读取缓冲：

```python
from minbt.plugins.binance import BinanceKlineCsvFeed, BinanceKlineIosqlFeed

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

result = exchange.run()  # auto：有序来源优先使用渐进回放
```

需要显式选择读取方式时，在这一次启动中指定 `load_mode="preload"` 或 `load_mode="incremental"`。比较不同模式需分别创建新的运行对象。

iosql 读取依赖 `query(..., order_by="open_time").iter_rows(...)` 的有序查询，
需要安装 iosql v0.3.x 或更新版本。`start/end` 在 minbt 中是半开区间 `[start, end)`；
iosql 的闭区间会由 Feed 自动转换。完整示例见 `examples/14_csv_feed.py` 和
`examples/15_iosql_feed.py`。

两个 Feed 默认进行数据完整性预检：显式请求的 symbol 必须在指定区间内有数据；
CSV 请求月份不能缺文件；iosql 的 interval/table 必须存在且表契约可查询。检查失败会
在策略开始前抛出带参数上下文的异常，不会静默完成空回测。

渐进回放用额外的迭代与归并开销换取更低的历史行情内存；全量预加载适合小数据和速度优先的
场景。具体速度和内存取决于来源、时间批次大小和数据字段。

如果存储的是 OrderBook、Trade、Price 或自定义 Bar，使用通用信封：

```python
from minbt.plugins.storage import CsvBarFeed

exchange.add_feed(CsvBarFeed("/path/to/bars.csv"))
```

通用 CSV/iosql Feed 只要求 `dt`、`symbol`、`kind`、`data`，不会把数据强制解释成 OHLCV。
其中 `symbols` 是筛选条件，允许部分标的没有命中；Binance 专用 Feed 会检查每个请求标的。

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
价格；先按数据族排序，同族内优先级较高的 Feed 先回调，相同优先级按注册顺序。
同优先级来源在同一时间、同一数据族、同一 symbol 真正重叠时会记录 warning 日志；需要
诊断时启用 minbt 日志。

自定义 Feed 的最小要求是唯一的非空 `name` 和产出 `Bar`/`News` 实例的 `events()`。
只实现这两项时，默认允许全量预加载；若事件已按时间非递减排列，且可以逐条读取，可声明
`supports_incremental=True` 和 `ordered=True`，让 `auto` 优先选择渐进回放。
`auto` 要求所有来源都支持有序渐进回放，否则尝试所有来源的预加载能力；不满足时直接报错。
`prepare()` 和 `close()` 为可选资源钩子。模式比较见 [16_replay_modes.py](examples/16_replay_modes.py)。

例如使用交易所 mark price 计算盈亏：

```python
broker = Broker(
    initial_cash=10_000,
    mark_price="price.value",
)
```

普通 Kline 回测不需要配置 `mark_price`，`Broker(initial_cash=...)` 默认使用 `kline.close`。推荐使用字符串形式，
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
- 显式 `price` 同时更新该标的的当前最新价；后续市场批次仍按 Broker 的 `mark_price` 重新估值。
- 价格、数量、目标、资金、杠杆及退出数值必须为有限实数，非法类型或范围在账户修改前抛出异常。
- 回放中沿用旧报价成交时，市场规则、成交记录和 T+1 均使用当前回放时间；
  `get_last_price(..., return_dt=True)` 返回报价时间，显式 `price_dt` 也不能倒退运行中的交易时钟。

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
显式价格先推进风险，再按最新持仓计算目标差额；目标比例使用风险结算后的权益。

### 平仓

```python
self.broker.close_position("BTCUSDT", price=105)
self.broker.close_portfolio("trend")
```

- `close_position()` 全平指定标的净持仓。
- 如果显式价格先触发强平，清仓或目标归零返回 skipped，最终保持零敞口。
- `close_portfolio()` 原子关闭指定 portfolio；任一仓位不能关闭时，不执行任何平仓。
- 普通全平按整组平仓金额和手续费一次结算，不受亏损腿与盈利腿的持仓顺序影响。
- `close_portfolio()` 成功后同时取消该 portfolio 的 pending 限价单；预检失败时订单保持
  pending，避免出现活动订单指向已删除 portfolio。

全仓模式的纯减仓（不反手）按整个分仓的权益承担亏损。扣费后的权益足够时，减仓可以产生
负现金余额，`get_cash()` 直接显示这笔已实现欠款。其他持仓的保证金和未实现盈亏继续支撑账户，
后续风险检查仍会强平或穿仓结算。欠款期间禁止新开仓、加仓、反手和划出资金；盈利腿平仓及
其他分仓归还的现金可分次偿还欠款。逐仓模式保持独立的风险与现金约束，所有成交仍遵守交易时间、整手和 T+1。

金额预检和提交使用相同的浮点尾差规则；零手续费的满仓目标不会因尾差拒单。输入或派生金额
溢出时会在成交前拒绝，不留下部分持仓、现金或未完成市价单。

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

撤单会更新原订单的状态及 `updated_dt`，并返回独立的 `source="cancel_order"` 动作订单；
动作的 `created_dt/updated_dt` 使用当前交易时钟，账户没有时钟时为 `None`。

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
- 成交价使用提交的 `limit_price`，不因最新价更有利而改善。例如买入限价 95，最新价跌至 94 时仍以 95 成交。
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
同一净持仓生命周期只有一份有效保护。加仓附带条件，以及用任一当前订单调用 `set_exit/add_exit`，
都保留未修改的标准条件、函数规则和函数 state；`clear_exit()` 才显式删除条件。
全平、反转或强平结束旧生命周期，旧订单不能修改新仓保护。

### 持仓中修改

```python
self.broker.set_exit(
    order.id,
    stop_loss_price=price * 0.98,
    take_profit_price=price * 1.12,
)
```

`clear_exit(order.id)` 默认清除全部退出条件。只清除追踪止损、保留其他条件时，显式关闭
其余清除开关：

```python
self.broker.clear_exit(
    order.id,
    stop_loss_price=False,
    take_profit_price=False,
    trailing_stop=True,
    custom=False,
)
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
该预设允许工作日午夜时间的日线 Bar，不检查节假日；日内数据仍按交易时段校验。

跨市场分仓：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.0005, market=markets.CRYPTO)
broker.add_portfolio("ashare", cash=60_000)
broker.add_portfolio("crypto", cash=40_000)
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])

self.broker.order_target_percent("600519.SH", 0.8, price=a_price, portfolio="ashare")
self.broker.order_target_percent("BTCUSDT", 0.8, price=btc_price, portfolio="crypto")
```

分仓名称必须是非空白字符串，非法名称在资金划拨前抛错。

## 结果查询

当前盈亏由库统一统计：

```python
pnl = broker.get_total_pnl()
print(pnl.net_pnl, pnl.realized_pnl, pnl.unrealized_pnl, pnl.fees)

broker.get_pnl()  # main 分仓
broker.get_pnl("BTCUSDT", portfolio="trend")
broker.get_total_pnl("BTCUSDT")  # 跨分仓汇总标的
records = broker.get_pnl_records(portfolio="main", symbol="BTCUSDT")
order_records = broker.get_pnl_records(order_id=order.id)
```

返回的 `Pnl` 是不可变快照：已实现盈亏按平均成本计算，未实现盈亏按最新估值计算，两者均为毛盈亏；
`fees` 是实际累计支付的全部手续费。普通交易满足 `net_pnl = realized_pnl + unrealized_pnl - fees`。
穿仓时另有 `settlement_adjustment`，`net_pnl` 会自动包含它，与实际清零后的权益对齐。
全账户净盈亏等于 `broker.get_total_equity() - broker.initial_cash`。

分仓划拨不计为盈亏，已关闭分仓及同名重建后的历史仍保留原归属。因此主分仓和同名重建分仓的累计净盈亏，
不能直接用其当前权益减初始资金计算。全仓穿仓的账户结算调整没有标的归属，按标的汇总时不包含这部分调整。

`PnlRecord` 每条记录对应一次实际成交或系统风险结算，包含分仓、标的、数量、价格、时间、订单 ID 和盈亏金额，
按实际记账顺序返回。开仓记录的净贡献可能只有手续费；不配对 FIFO 往返交易，也不分摊过去的开仓手续费。
系统结算没有订单 ID，强平沿用现有免手续费规则。未知标的返回零值或空明细，未知分仓抛出 `ValueError`。

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
可直接运行 `examples/11_pnl.py` 查看多头、空头和手续费场景的库级查询结果与曲线。

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

示例文件名采用 `两位序号_用途.py`，编号表示推荐阅读顺序，例如 `01_quickstart.py`、`02_moving_average.py`、`03_rotation.py`。
每个示例可独立运行，直接使用 minbt 和 Matplotlib，按需使用标准库读取或生成数据。`01_quickstart.py` 使用两条内联行情；Feed 示例需要对应的数据源，其中 Binance 示例需要网络，CSV 示例需要配置数据目录，iosql 示例还需要安装 iosql 并配置数据库 URI。

推荐按顺序阅读：

```bash
python examples/01_quickstart.py
python examples/02_moving_average.py
python examples/03_rotation.py
python examples/04_exit_rules.py
python examples/05_limit_orders.py
python examples/06_breakout.py
python examples/07_rebalance.py
python examples/08_pairs_trading.py
python examples/09_cross_market.py
python examples/10_run_control.py
python examples/11_pnl.py
python examples/12_benchmark.py
python examples/13_binance_feed.py
python examples/14_csv_feed.py
python examples/15_iosql_feed.py
python examples/16_replay_modes.py
python examples/17_bar_storage.py
python examples/18_config_run.py
```

示例文件：

- [examples/01_quickstart.py](./examples/01_quickstart.py)：最小回测，使用两条行情买入并持有。
- [examples/02_moving_average.py](./examples/02_moving_average.py)：单标的双均线趋势跟随。
- [examples/03_rotation.py](./examples/03_rotation.py)：多标的横截面动量轮动。
- [examples/04_exit_rules.py](./examples/04_exit_rules.py)：订单附带止盈止损和追踪止损。
- [examples/05_limit_orders.py](./examples/05_limit_orders.py)：限价单、成交和撤单。
- [examples/06_breakout.py](./examples/06_breakout.py)：单标的趋势突破。
- [examples/07_rebalance.py](./examples/07_rebalance.py)：多标的轮动和再平衡。
- [examples/08_pairs_trading.py](./examples/08_pairs_trading.py)：配对均值回归。
- [examples/09_cross_market.py](./examples/09_cross_market.py)：一个 Broker 内同时交易 A 股和 crypto。
- [examples/10_run_control.py](./examples/10_run_control.py)：暂停、继续和退出回测，查询结果快照。
- [examples/11_pnl.py](./examples/11_pnl.py)：展示多空盈亏、手续费和订单记账明细。
- [examples/12_benchmark.py](./examples/12_benchmark.py)：10 万行空策略基准。
- [examples/13_binance_feed.py](./examples/13_binance_feed.py)：自动下载、缓存并回放 Binance futures K 线。
- [examples/14_csv_feed.py](./examples/14_csv_feed.py)：渐进读取 crypto.bn_data_sync 月度 CSV K 线。
- [examples/15_iosql_feed.py](./examples/15_iosql_feed.py)：使用 iosql 有序查询渐进回放 K 线。
- [examples/16_replay_modes.py](./examples/16_replay_modes.py)：分别新建实验比较 auto/preload/incremental，展示通用 Bar、Feed 优先级和 Broker 估值来源。
- [examples/17_bar_storage.py](./examples/17_bar_storage.py)：通用 Bar CSV 存储和自定义 Bar 回调。
- [examples/18_config_run.py](./examples/18_config_run.py)：策略类、JSON 配置与自备数据工厂，从结果快照绘图。
- [examples/data.csv](./examples/data.csv)：单标的 BTCUSDT 示例行情。

## Codex Skill

minbt 安装包包含面向策略开发的 `minbt-usage` skill，源码位于
[minbt/skills/minbt-usage](./minbt/skills/minbt-usage/SKILL.md)。skill、参考资料和最小脚本随
wheel 与 sdist 一起发布，安装、升级或降级时使用对应版本的内容。

用项目实际运行策略的 Python 查询安装版本和 skill 的绝对目录：

```bash
python -m minbt.skills
python -m minbt.skills --path  # 只输出 minbt-usage 目录
```

普通安装的目录位于当前环境的 `site-packages/minbt/skills/minbt-usage/`；editable 开发安装
指向源码中的同一目录。Python 中也可调用 `from minbt.skills import get_skill_path`。
源码开发先执行 `pip install -e .`，让安装元数据与当前源码一致。

Codex 从项目或用户的 `.agents/skills/` 等位置发现本地 skill，并支持符号链接。
在消费项目中，可将项目级链接指向当前 Python 环境的资源：

```bash
mkdir -p .agents/skills
ln -s "$(python -m minbt.skills --path)" .agents/skills/minbt-usage
```

使用项目的虚拟环境执行上面的命令。已有同名目录或链接时，先确认它的用途再调整；
更换虚拟环境或切换普通/editable 安装后重新建立链接。同一环境中普通安装的版本升级或降级时，
链接继续指向该环境的安装资源。
minbt 仓库自身的 `.agents/skills/minbt-usage` 使用相对链接指向包内源码。
发现机制见 [OpenAI 文档](https://learn.chatgpt.com/docs/build-skills)。

安装包中还包含不依赖绘图、网络或外部数据的最小验证脚本。
将目录替换为 `--path` 输出，即可从任意工作目录运行：

```bash
python /path/to/minbt-usage/scripts/quickstart.py
```

结果为 `final_equity=1020.00`。接入本地发现后，可以使用：

```text
Use $minbt-usage to write a minbt strategy for my CSV data.
```

该 skill 帮助 Agent 检查数据结构、生成 `Strategy`、通过 Broker 下单、设置退出条件并核对结果。
说明只描述该版本已实现的接口，所有必要资料均在 skill 目录内。
框架开发的接口边界见 [设计规范](docs/design/protocols/README.md)。

发布前执行安装包回归测试：

```bash
python -m pytest -q tests/test_skill_packaging.py
```

测试从干净副本构建 wheel、sdist 和 sdist 派生的 wheel，比对全部 skill 资源，并在仓库外
安装及运行定位入口与最小策略。公开接口变化时，同时维护 skill 与可执行示例。

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

## 发布到 PyPI

发布流程位于 [`.github/workflows/release.yml`](./.github/workflows/release.yml)。发布新版本前，先更新
`pyproject.toml` 的 `[project].version` 并推送代码，然后在 GitHub 创建对应的 Release，标签格式为
`vX.Y.Z`，且必须和项目版本完全一致。发布 Release 后，Actions 会运行全量测试、构建 wheel 和 sdist、
检查发行包，再上传到 PyPI。

首次启用时配置一次 Trusted Publishing：

1. 在 GitHub 仓库的 Settings → Environments 中创建名为 `pypi` 的环境；可按需配置审批人，并将允许部署的
   tag 限制为 `v*`。
2. 在 PyPI 项目的 Publishing 设置中新增 GitHub Publisher：owner 为 `gseismic`，repository 为 `minbt`，
   workflow 为 `release.yml`，environment 为 `pypi`。如果 PyPI 上还没有该项目，则添加 pending publisher。

工作流使用 OIDC 短期凭据，不需要创建或保存 PyPI API Token。构建和发布分属不同 job，只有发布 job 获得
`id-token: write` 权限。

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

- [@2026-10-12] v0.1.1：随安装包发布 `minbt-usage` skill，新增资源定位入口和发行物回归测试；配置 GitHub Release 触发的 PyPI Trusted Publishing 发布流程。
- [@2026-10-02] v0.1.0：修复逐仓风控、市场时区与交易单位校验、持仓查询副作用、挂单触发、退出条件继承和数据 Feed/缓存边界；支持显式时间戳单位。
- [@2026-06-24] v0.0.4：修复全仓保证金、总权益统计、日志参数和 Python 3.8 注解兼容问题。
- [@2024-11-16] v0.0.3 release。
