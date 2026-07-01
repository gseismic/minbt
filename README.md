# minbt

minbt 是一个最简回测框架。目标不是模拟完整交易所，而是让用户用少量代码完成：

1. 准备历史数据。
2. 实现 `Strategy` 回调。
3. 在策略里调用 `self.broker` 交易。
4. 查看现金、持仓、订单和权益结果。

当前主路径是多标的 K 线或类似 bar 数据：`Exchange.set_bars(data)` + `Strategy.on_bars(dt, bars)` + `Broker` 下单。

## 特性

- 支持 pandas、polars 和 `list[dict]` 数据输入。
- 支持多标的同一时间截面回调：`on_bars(dt, bars)`。
- 支持市价单、限价单、撤单和订单状态。
- 支持目标持仓、目标名义金额、目标权重调仓。
- 支持多空双向、动态杠杆、全仓和逐仓保证金。
- 支持多 portfolio 分仓。
- 支持订单级止损、止盈、追踪止损和函数式退出条件。
- 支持市场特征配置和按 symbol 路由：默认 T+0、加密资产、A 股 T+1 预设。
- 自动记录策略权益和持仓历史。

## 安装

从源码目录安装：

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
```

`pyta2` 用于更高效的历史向量存储；未安装时会自动回退为 Python list。`plot` 额外依赖只在绘图时需要。

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

推荐使用：

```python
exchange.set_bars(data, date_key="dt", symbol_key="symbol", price_key="close")
```

`data` 支持：

- `pandas.DataFrame`
- `polars.DataFrame`
- `list[dict]`

bars 必需字段：

- `dt`: 回测时间，字段名可用 `date_key` 改。
- `symbol`: 标的代码，字段名可用 `symbol_key` 改。
- `close`: 当前 bar 用于更新最新价的价格，字段名可用 `price_key` 改。

关键规则：

- 同一 `(dt, symbol)` 只能有一条 bar。
- Exchange 会按时间排序并在每个 `dt` 聚合完整截面。
- 同一 `dt` 下，所有标的价格先整体更新，再处理限价单和退出条件，最后调用策略回调。
- 不提供 `date_key=None` 或行号时间；时间字段必须显式存在。

除 bars 外，Exchange 还支持相同时间截面模型的数据入口：

- `set_books(data, date_key="dt", symbol_key="symbol", price_key=None)`
- `set_trades(data, date_key="dt", symbol_key="symbol", price_key="price")`
- `set_news(data, date_key="dt")`

回调顺序固定为：

```text
on_bars -> on_books -> on_trades -> on_news
```

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

市场预设：

```python
from minbt import Broker, markets

broker = Broker(initial_cash=100_000, fee_rate=0.0005, market=markets.CRYPTO)
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH", "510300.SH"])
```

`market` 是默认市场规则，未通过 `add_market(...)` 显式映射的 symbol 使用默认规则。上例中 `600519.SH` 和 `510300.SH` 使用 A 股规则，`BTCUSDT` 等未映射 symbol 使用 crypto 规则。

`add_market(...)` 应在回测运行和任何交易发生前调用。查询某个 symbol 使用的市场规则时使用 `broker.get_market(symbol)`，返回的是快照，不能通过修改返回对象改变 broker 内部规则。

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

也可以直接从 broker 查询当前状态：

```python
broker.get_total_equity()
broker.get_cash()
broker.get_position_sizes()
broker.get_orders()
```

## 示例

推荐按顺序阅读：

```bash
python examples/01_demo_mini.py
python examples/02_single_symbol_sma.py
python examples/03_multi_symbol_rotation.py
python examples/04_scenario_exit_rules.py
python examples/05_scenario_limit_order.py
python examples/06_scenario_single_breakout.py
python examples/07_scenario_multi_rotation.py
python examples/08_scenario_pairs_mean_reversion.py
python examples/09_benchmark_100k_empty.py
python examples/10_scenario_cross_market.py
```

示例文件：

- [examples/01_demo_mini.py](./examples/01_demo_mini.py)：最小单标的示例。
- [examples/02_single_symbol_sma.py](./examples/02_single_symbol_sma.py)：单标的双均线趋势跟随。
- [examples/03_multi_symbol_rotation.py](./examples/03_multi_symbol_rotation.py)：多标的横截面动量轮动。
- [examples/04_scenario_exit_rules.py](./examples/04_scenario_exit_rules.py)：订单附带止盈止损和追踪止损。
- [examples/05_scenario_limit_order.py](./examples/05_scenario_limit_order.py)：限价单、成交和撤单。
- [examples/06_scenario_single_breakout.py](./examples/06_scenario_single_breakout.py)：单标的趋势突破。
- [examples/07_scenario_multi_rotation.py](./examples/07_scenario_multi_rotation.py)：多标的轮动和再平衡。
- [examples/08_scenario_pairs_mean_reversion.py](./examples/08_scenario_pairs_mean_reversion.py)：配对均值回归。
- [examples/09_benchmark_100k_empty.py](./examples/09_benchmark_100k_empty.py)：10 万行空策略基准。
- [examples/10_scenario_cross_market.py](./examples/10_scenario_cross_market.py)：一个 Broker 内同时交易 A 股和 crypto。
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
pytest -q
```

运行编译检查：

```bash
python -m compileall -q minbt tests examples
```

当前环境可能出现 `Polars binary is missing!` warning；只要测试未失败，就按环境依赖警告处理。

## 设计边界

minbt 当前明确不做：

- 不拉取或缓存历史行情，用户自行准备数据。
- 不模拟滑点、订单簿队列位置和部分成交。
- 不根据 bar 的 `high/low` 推断 intrabar 路径。
- 不模拟完整交易所风控、撮合和真实订单生命周期。
- 不支持初始持仓复杂初始化。
- 不支持多批次持仓分别维护独立止盈止损。

当前资金模型是保证金账户模型。`Position.equity` 表示保证金加未实现盈亏，不是现货市值。

## ChangeLog

- [@2026-06-24] v0.0.4：修复全仓保证金、总权益统计、日志参数和 Python 3.8 注解兼容问题。
- [@2024-11-16] v0.0.3 release。
