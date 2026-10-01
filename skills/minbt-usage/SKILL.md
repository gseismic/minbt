---
name: minbt-usage
description: This skill should be used when the user asks to "write a minbt strategy", "run a minbt backtest", "adapt OHLCV or bar data for minbt", or "debug minbt orders or PnL", or mentions Exchange.set_bars, Exchange.add_feed, Strategy.on_bars/on_bar, Broker orders, target positions, exits, limit orders, portfolios, markets, CSV/iosql/Binance feeds, or minbt examples. It distinguishes the current runnable API from the pending target API design. Do not use it for implementing minbt internals.
---

# minbt Usage

本 skill 面向“用户使用 minbt 写策略”，不是内部框架开发文档。默认目标是用最少代码完成一个可运行、可验证的回测。

## 文档状态（先读）

本文件描述的是**当前代码中可以运行的接口**。本轮 API 重构的目标设计记录在
`docs/design/minbt-20260921-api-refactor.md`，目前仍是设计稿，尚未替换当前实现；不要把目标签名
直接复制到当前策略中。

| 主题 | 当前可运行实现 | 目标设计（待实施） |
| --- | --- | --- |
| K 线回调 | `on_bars(dt, bars)`，并兼容 `on_bar` | 只保留 `on_bars` |
| 其他数据 | `on_books`、`on_trades`、`on_news` | 保持这些按数据类型的入口 |
| 价格字段 | Broker 的 `mark_price`（默认 `kline.close`） | 数据入口的 `price_key`，默认值为 `close` |
| 回放配置 | `run(load_mode=...)` 可用 | 隐藏回放模式，用户只需 `run()` |
| 通用 Bar | 当前实现和 `examples/400_exchange_replay_modes.py`、`examples/401_exchange_generic_bar_storage.py` 仍使用 `Bar.kind` | 移除通用 `Bar` 概念，保留按类型的数据入口 |

因此，写**当前可执行代码**时遵循下文的“当前实现”说明；讨论或编写新设计时遵循目标设计，
不要继续扩大 `on_bar`、`Bar.kind`、`mark_price`、`load_mode` 这些兼容接口的使用面。

## 用户心智模型

用户只需要理解四个核心对象：

- `Exchange`: 接收历史数据并推进回测时间。
- `Strategy`: 用户写交易逻辑。
- `Broker`: 策略里的唯一交易入口。
- `Order`: 下单结果，也是修改退出条件的句柄。

稳定主路径：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001)
strategy = MyStrategy(strategy_id="demo", broker=broker)

exchange = Exchange()
exchange.set_bars(data)
exchange.add_strategy(strategy)
exchange.run()
```

## 安装与测试

minbt 使用 `pyproject.toml` 管理安装和测试配置，不使用 `setup.py`，也不需要单独维护 `pytest.ini`。

源码目录开发安装：

```bash
pip install -e .
```

可选依赖：

```bash
pip install -e ".[pyta]"
pip install -e ".[plot]"
pip install -e ".[dev]"
```

- `pyta`: 安装 `pyta2`，用于更高效的历史向量存储。
- `plot`: 安装 Matplotlib 绘图依赖；运行示例默认弹出图表窗口并保存截图，关闭窗口后继续退出。
- `dev`: 安装 pytest，用于运行测试。

## 策略开发工作流

1. 先确认用户数据结构：时间列、标的列和市场字段。
2. 本地已有数据时优先使用 `Exchange.set_bars(data, date_key="dt", symbol_key="symbol")`。
3. 需要自动下载和复用行情时，使用 `Exchange.add_feed(feed)`，例如 `minbt.data.binance.BinanceKlineFeed`。
4. 继承 `Strategy`，在 `on_init()` 初始化状态。
5. 在 `on_bars(dt, bars)` 读取当前时间截面；`on_bar` 只用于当前通用 Bar 的兼容场景。
6. 只通过 `self.broker` 下单和查询状态。
7. 用 `Order.status` 判断下单结果，不依赖 `reason` 精确文本。
8. 给用户提供最小运行命令和验证命令。

## 回调与数据入口

默认使用 `set_bars()` 接入已在内存中的 bars 数据。需要其他事件类型时，使用对应的公开入口：

```python
exchange.set_books(data, date_key="dt", symbol_key="symbol")
exchange.set_trades(data, date_key="dt", symbol_key="symbol")
exchange.set_news(data, date_key="dt", symbol_key="symbol")
```

在策略中实现对应回调：`on_bars(dt, bars)`、`on_books(dt, books)`、`on_trades(dt, trades)`、
`on_bar(dt, bar)`、`on_news(dt, news)`。同一 `dt` 下先收齐完整时间批次，再由 Broker 按
`mark_price` 选择估值价格并批量更新账户，随后处理待处理订单和退出条件，最后按
`bars → books → trades → bar → news` 顺序调用策略回调。

`on_bar` 面向当前实现中的 `Bar.kind`，按单个事件逐条调用，不把同一 `dt` 的多个自定义 Bar
聚合成截面。它仅为兼容现有代码保留；普通新策略不要选择它。`mark_price="kind.field"` 是当前
实现的推荐形式；元组和 callable 属于高级用法，其中
`(feed_name, kind, field)` 会耦合 Feed 名称，只有需要精确路由时使用。

目标设计中的 `price_key` 尚未实现，当前不能写成
`exchange.set_bars(data, price_key="price")`。如果数据没有 `close`，当前实现应在 Broker 中配置
`mark_price`，或在下单时显式传入 `price`；迁移到目标设计后再改用数据入口的 `price_key`。

普通用户只需要 `exchange.run()`。需要控制内存/速度时，再使用 `load_mode`：

```python
exchange.run()                         # auto
exchange.run(load_mode="preload")      # 全量预加载，速度优先
exchange.run(load_mode="incremental")  # 渐进回放，内存优先
```

`stream` 只保留给未来实时模式，不用于历史回放。`load_mode` 是当前实现的高级选项，不要在新
用户示例中继续传播；目标设计会将回放模式收回内部。

如果用户要求写示例，优先参考：

运行示例前确认 minbt 已安装；所有示例直接导入已安装的包。图表依赖通过 `pip install -e ".[plot]"` 安装。

- `examples/000_core_pnl_sanity_check.py`: 可手算的多空、手续费和净盈亏曲线校验。
- `examples/001_core_demo_mini.py`: 最小单标的。
- `examples/002_core_single_symbol_sma.py`: 单标的均线。
- `examples/003_core_multi_symbol_rotation.py`: 多标的横截面轮动。
- `examples/100_scenario_exit_rules.py`: 订单级退出条件。
- `examples/101_scenario_limit_order.py`: 限价单。
- `examples/102_scenario_single_breakout.py`: 单标的真实场景。
- `examples/103_scenario_multi_rotation.py`: 多标的轮动。
- `examples/104_scenario_pairs_mean_reversion.py`: 配对均值回归。
- `examples/105_scenario_cross_market.py`: 一个 Broker 内同时交易 A 股和 crypto。
- `examples/200_benchmark_100k_empty.py`: 10 万行空策略基准。
- `examples/300_feed_crypto_binance.py`: 自动下载、缓存并回放 Binance futures K 线。
- `examples/301_feed_csv.py`: 渐进读取月度 CSV K 线。
- `examples/302_feed_iosql.py`: 渐进读取 iosql K 线。
- `examples/400_exchange_replay_modes.py`: 当前兼容 API 的通用 Bar、Feed 优先级和 Broker 估值来源。
- `examples/401_exchange_generic_bar_storage.py`: 当前兼容 API 的通用 Bar CSV 存储和自定义 Bar 回调。

`examples/400_exchange_replay_modes.py` 和 `examples/401_exchange_generic_bar_storage.py` 用来验证现有兼容面，不代表目标 API 的推荐写法。

## 数据契约

当前实现的默认估值路径要求 Kline 行数据至少包含：

```text
dt, symbol, close
```

规则：

- `data` 可以是 pandas DataFrame、polars DataFrame 或 `list[dict]`。
- 单标的也是多标的的特例，仍建议保留 `symbol` 列。
- 同一 `(dt, symbol)` 只能有一条 bar。
- 策略回调收到的 `dt` 会统一为 UTC `datetime.datetime`。
- Kline 不强制完整 OHLCV；默认 Broker 使用 `close` 估值。若使用其他字段，当前实现需要配置
  `mark_price` 或在下单时传入 `price`。
- Exchange 不根据 Feed 优先级选择盈亏价格。
- 不要使用行号代替时间；`date_key` 必须存在。

目标设计会把“哪一列是价格”移到 `set_bars`/`set_books`/`set_trades` 的 `price_key` 参数；这只
是迁移方向，不是当前版本可调用的参数。

如果用户数据列名不同，映射参数即可：

```python
exchange.set_bars(data, date_key="date", symbol_key="ticker")
```

如果用户只有单标的 CSV 且缺少 `symbol` 列，可以在加载后补一列：

```python
data["symbol"] = "BTCUSDT"
exchange.set_bars(data, date_key="date", symbol_key="symbol")
```

## 自动下载行情

用户不想手工准备 CSV 时，可以使用 Binance futures 历史 K 线 feed：

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

第一次运行会自动下载并写入 `{cache_dir}/minbt-data.sqlite3`，后续相同区间复用本地缓存。策略仍然只写：

```python
def on_bars(self, dt, bars):
    price = bars["BTCUSDT"]["close"]
    self.broker.order_target_percent("BTCUSDT", 0.8, price=price)
```

如果用户要求完全离线运行，可以传 `cache_only=True`。缓存不存在或覆盖不完整时会报错，不会创建空缓存。
该 Binance Feed 当前在准备阶段读取缓存查询结果，默认适合全量预加载；需要渐进回放时使用 CSV 或
iosql Feed。

## 渐进读取 CSV / iosql

数据来自 `crypto.bn_data_sync` 月度 CSV 或 iosql 库时，使用支持渐进回放的 Feed：

```python
from minbt.data import BinanceKlineCsvFeed, BinanceKlineIosqlFeed

exchange.add_feed(BinanceKlineCsvFeed(
    root="/path/to/kline.csv/1m",
    symbols=["BTCUSDT"],
    interval="1m",
    start="2023-01-01",
    end="2023-01-03",
))

# 或：BinanceKlineIosqlFeed("sqlite:///path/to/data.iosql", "1m", ...)
exchange.run()
```

`start/end` 使用半开区间 `[start, end)`；iosql 的闭区间查询由 Feed 自动转换。两个 Feed
在策略启动前检查数据完整性：请求 symbol、CSV 月份、iosql table/interval 或时间范围没有
数据时直接报错，不会静默运行空回测。`BinanceKlineIosqlFeed` 需要安装 `iosql` 0.3.x 或更新版本，
`batch_size` 只用于调整数据库读取缓冲。渐进回放节省历史数据内存，但会增加归并与迭代耗时；
全量预加载适合小数据和速度优先的场景。

如果 CSV/iosql 存储的是 OrderBook、Trade、Price 或自定义 Bar，使用通用 `CsvBarFeed` 或
`IosqlBarFeed`。通用存储至少包含 `dt,symbol,kind,data`，其中 `data` 是 JSON；Kline 专用
`BinanceKlineCsvFeed`、`BinanceKlineIosqlFeed` 继续用于 Binance Kline 文件和表。

## Strategy 模板

最小策略模板：

```python
from minbt import Broker, Exchange, Strategy


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

    def on_finish(self):
        print("equity:", self.broker.get_total_equity())
        print("positions:", self.broker.get_position_sizes())
```

多标的横截面策略模板：

```python
class RotationStrategy(Strategy):
    def on_init(self):
        self.history = {}

    def on_bars(self, dt, bars):
        for symbol, row in bars.items():
            self.history.setdefault(symbol, []).append(row["close"])

        scores = {}
        for symbol, prices in self.history.items():
            if len(prices) >= 20:
                scores[symbol] = prices[-1] / prices[-20] - 1

        if not scores:
            return

        selected = max(scores, key=scores.get)
        for symbol, row in bars.items():
            target = 0.8 if symbol == selected else 0.0
            self.broker.order_target_percent(symbol, target, price=row["close"])
```

## Broker 交易接口

优先使用目标仓位接口：

```python
self.broker.order_target_size(symbol, target_size=1, price=price)
self.broker.order_target_value(symbol, target_value=10_000, price=price)
self.broker.order_target_percent(symbol, target_percent=0.8, price=price)
```

需要精确增量时使用市价单：

```python
self.broker.submit_market_order(symbol, qty=1, price=price)
```

平仓：

```python
self.broker.close_position(symbol, price=price)
self.broker.close_portfolio("trend")
```

`close_portfolio()` 成功时会同时取消该组合的 pending 限价单；关闭预检失败时不会撤单。

限价单：

```python
order = self.broker.submit_limit_order(symbol, qty=1, limit_price=95)
self.broker.cancel_order(order.id)
```

订单结果：

```python
order = self.broker.order_target_percent(symbol, 0.8, price=price)
if order.status == "filled":
    ...
elif order.status == "rejected":
    ...
```

不要依赖 `reason` 的精确字符串。

常见订单状态为 `filled`（成交）、`pending`（限价单挂起）、`canceled`（已撤销）、`rejected`
（资金或市场规则拒绝）和 `skipped`（目标仓位未变化）。稳定逻辑优先读取 `status`、`qty`、
`filled_qty`、`avg_price` 等结构化字段。

限价单按当前最新价触发，不根据 bar 的 `high/low` 推断 intrabar 路径。买入限价单在最新价
小于等于 `limit_price` 时触发，卖出限价单在最新价大于等于 `limit_price` 时触发；提交时和触发
时都会检查资金与市场规则，pending 期间不预留资金，也不模拟排队和部分成交。`close_portfolio()`
成功后取消该 portfolio 的 pending 限价单，关闭预检失败时保持 pending。

历史查询始终返回 Python `list`：

```python
equity = strategy.get_hist_equity()
sizes = strategy.get_hist_position_sizes(symbol)
```

从未交易的 symbol 返回与权益历史等长的全零列表；安装 pyta2 只改变内部存储。

净盈亏曲线可以直接由权益曲线计算。应在回测前保存初始权益：

```python
initial_equity = broker.get_total_equity()
exchange.run()
pnl_curve = [equity - initial_equity for equity in strategy.get_hist_equity()]
```

定义为 `pnl(t) = equity(t) - initial_equity`。正值表示盈利，负值表示亏损；持仓未平时包含按最新价
盯市的未实现盈亏，最终结果包含手续费。在默认杠杆、单次完整开平仓且没有其他成交的示例中，可用
`gross_pnl = qty * (exit - entry)`、
`fees = (abs(qty) * entry + abs(qty) * exit) * fee_rate`、
`net_pnl = gross_pnl - fees` 独立核对。需要确认计算是否正确时，优先运行
`examples/000_core_pnl_sanity_check.py`，它会把理论手算值和实际回测值同时打印并绘制零盈亏基线。

## 退出条件

推荐在提交订单时设置固定退出价和追踪止损：

```python
order = self.broker.order_target_percent(
    symbol,
    0.8,
    price=price,
    stop_loss_price=price * 0.95,
    take_profit_price=price * 1.10,
    trailing_stop_pct=0.05,
)
```

持仓中修改：

```python
self.broker.set_exit(order.id, stop_loss_price=price * 0.98)
self.broker.clear_exit(order.id, trailing_stop=True)
```

复杂退出条件使用函数式退出：

```python
def exit_if_breaks_support(ctx):
    return ctx.price < ctx.state["support"]


self.broker.add_exit(
    order.id,
    name="support_break",
    condition=exit_if_breaks_support,
    state={"support": price * 0.96},
)
```

规则：

- `trailing_stop_pct` 和 `trailing_stop_amount` 互斥。
- 固定止损/止盈可以和追踪止损同时存在。
- 函数返回 `True` 表示退出当前 `portfolio + symbol` 净持仓。
- `Order` 只有在仍属于当前净持仓生命周期时才能新增或修改退出规则。

## Portfolio 与 Market

分仓：

```python
broker.add_portfolio("trend", cash=60_000)
self.broker.order_target_percent("BTCUSDT", 0.8, price=price, portfolio="trend")
```

市场预设：

```python
from minbt import Broker, markets

broker = Broker(initial_cash=100_000, fee_rate=0.0005, market=markets.CRYPTO)
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH", "510300.SH"])
```

`market` 是默认市场规则。未通过 `add_market(...)` 显式映射的 symbol 使用默认规则。`add_market(...)` 应在回测运行和任何交易发生前调用。查询 market 使用 `broker.get_market(symbol)`，不要使用或修改 `broker.market`。`markets.A_STOCK` 包含交易时间、100 股一手、价格 tick、不可做空和 T+1 持仓锁定。直接调用 broker 下单时需要传 `price_dt`；通过 Exchange 回测时，`dt` 会自动传入。

跨市场分仓：

```python
broker.add_portfolio("ashare", cash=60_000)
broker.add_portfolio("crypto", cash=40_000)
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])

self.broker.order_target_percent("600519.SH", 0.8, price=a_price, portfolio="ashare")
self.broker.order_target_percent("BTCUSDT", 0.8, price=btc_price, portfolio="crypto")
```

## 不推荐使用的内部接口

除非用户明确要开发 minbt 框架本身，否则不要在策略代码中使用：

- `Portfolio`、`Cash` 内部对象。
- `Broker.on_new_price(...)`。
- `Broker.process_pending_orders(...)`。
- `Broker.check_exit_rules(...)`。
- `Strategy.set_exchange(...)`。
- `Market.validate_order(...)` 等内部契约。

策略用户应通过 `Exchange.set_xx(...)` 接入数据，通过 `self.broker` 表达交易意图。

## 当前回测边界

写策略或解释结果时必须说明：

- 不模拟滑点。
- 不模拟订单簿队列位置。
- 不模拟部分成交。
- 不根据 bar 的 `high/low` 推断 intrabar 路径。
- 限价单和退出条件按当前最新价触发。
- 当前账户模型是保证金账户模型，`Position.equity` 不是现货市值。

## 验证命令

给用户生成或修改策略后，优先运行最小相关命令：

```bash
python examples/000_core_pnl_sanity_check.py
python examples/001_core_demo_mini.py
python -m pytest -q tests/test_pnl.py tests/test_examples.py
python -m pytest -q
python -m compileall -q minbt tests examples
git diff --check
```

如果只写了新的独立策略脚本，至少运行该脚本和 `python -m compileall -q`。

示例默认打开绘图窗口。脚本会等待用户关闭窗口后再退出；自动化运行只需要截图时，可设置 `MINBT_EXAMPLE_SHOW=0`。

当前环境可能出现 `Polars binary is missing!` warning；只要测试未失败，就按环境依赖警告处理。

## 示例覆盖与验证边界

测试时按示例的数据依赖区分，避免把外部数据缺失误判为代码错误：

- `000_core_*`、`100_scenario_*`、`400_exchange_*`：`tests/test_examples.py` 会在本地临时数据或 fake Feed 上运行。
- `200_benchmark_100k_empty.py`：单独检查 10 万行性能示例的输出。
- `300_feed_crypto_binance.py`：测试使用 fake Binance Feed；真实运行需要网络或已有缓存，不要求把
  远端服务作为单元测试前置条件。
- `301_feed_csv.py`、`302_feed_iosql.py`：需要通过 `MINBT_CSV_ROOT`、`MINBT_IOSQL_URI` 指定
  本地 fixture 或真实数据。数据缺失时示例会明确退出，而不是静默产生空结果。

推荐的完整检查顺序：

```bash
python -m pytest -q tests/test_examples.py
python -m compileall -q examples
# 准备 CSV/iosql 数据后再运行：
MINBT_CSV_ROOT=/path/to/kline.csv/1m python examples/301_feed_csv.py
MINBT_IOSQL_URI=sqlite:///path/to/kline.iosql python examples/302_feed_iosql.py
```

本次文档更新已用两行本地 CSV 和两行本地 iosql fixture 分别执行 12、13；二者均返回成功并输出
`final_equity` 与 `bar_count`。基线 `python -m pytest -q tests/test_examples.py` 覆盖其余示例路径。

## 文档更新原则

- README 和示例优先面向用户写策略，不讲内部状态机。
- 简单路径短，复杂功能渐进展开。
- 不恢复旧的 `on_data/on_tick/set_data` 入口；`on_bar` 只作为当前通用自定义 Bar 的兼容回调，
  不得成为新示例或新设计的主路径。
- 新接口文档必须明确标注“当前实现”与“目标设计”；目标设计未落地前，不得把 `price_key`、去
  `on_bar`、隐藏 `load_mode` 写成当前可运行 API。
- 不在 Strategy 上添加交易语法糖；交易统一通过 `self.broker`。
- 限价单、固定退出价、追踪止损和函数式退出已经实现，文档不要写成未实现。
