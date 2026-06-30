# minbt

minbt 是一个简易的量化回测框架，主要面向 T+0 的加密货币和其他高频换仓场景。项目刻意保持小规模代码量，核心目标是让用户用最少样板代码完成多空双向、市价撮合、保证金和分仓回测。

## 主要特点

- [x] 支持 pandas、polars 和 `list[dict]` 行情输入。
- [x] 支持市价单。
- [x] 支持多空双向持仓。
- [x] 支持动态杠杆。
- [x] 支持逐仓和全仓两种保证金模式。
- [x] 支持多 portfolio 分仓。
- [x] 自动记录策略权益和持仓历史。
- [x] 支持多标的同一时间截面的 `on_bars(dt, bars)` 回调。
- [x] 支持目标持仓、目标名义金额、目标权重调仓。
- [x] 支持限价单、撤单和订单状态管理。
- [x] 支持订单级止盈止损、追踪止损和函数式退出条件。
- [x] 支持最小市场规则扩展，包括默认 T+0、加密资产和 A 股 T+1 预设。

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
```

`pyta2` 可用于更高效的历史向量存储；未安装时 minbt 会自动回退为 Python list。

绘图示例需要额外安装：

```bash
pip install -e ".[plot]"
```

## 快速开始

下面示例使用内存行情数据完成一个最小回测。bars 行情至少需要 `dt`、`symbol` 和 `close` 三列，时间字段可通过 `date_key` 改名。Exchange 会按 `date_key` 和 `symbol` 稳定排序；同一个 `date_key` 下的全部标的价格会先完整更新，再触发策略回调；同一时间截面内同一个 `symbol` 只能出现一次。

```python
import pandas as pd
from minbt import Broker, Exchange, Strategy


class DemoStrategy(Strategy):
    def on_init(self):
        self.bar_count = 0

    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["close"]

        if self.bar_count == 0:
            self.broker.order_target_percent("BTCUSDT", 0.8, price=price, leverage=2)
        elif self.bar_count == 2:
            self.broker.close_position("BTCUSDT", price=price)

        self.bar_count += 1

    def on_finish(self):
        print("equity:", self.broker.get_total_equity())
        print("position:", self.broker.get_position_size("BTCUSDT"))


data = pd.DataFrame(
    [
        {"dt": "2026-01-01", "symbol": "BTCUSDT", "close": 100.0},
        {"dt": "2026-01-02", "symbol": "BTCUSDT", "close": 110.0},
        {"dt": "2026-01-03", "symbol": "BTCUSDT", "close": 120.0},
    ]
)

exchange = Exchange()
exchange.set_bars(data, date_key="dt")

broker = Broker(initial_cash=10_000, fee_rate=0.001, leverage=2.0)
strategy = DemoStrategy(strategy_id="demo", broker=broker)

exchange.add_strategy(strategy)
exchange.run()
```

也可以直接运行仓库示例。推荐按复杂度从 mini 到策略示例逐步看：

```bash
python examples/01_demo_mini.py
python examples/02_single_symbol_sma.py
python examples/03_multi_symbol_rotation.py

# 更接近真实研究场景的示例
python examples/04_scenario_exit_rules.py
python examples/05_scenario_limit_order.py
python examples/06_scenario_single_breakout.py
python examples/07_scenario_multi_rotation.py
python examples/08_scenario_pairs_mean_reversion.py
```

示例文件：

- [examples/01_demo_mini.py](./examples/01_demo_mini.py)：最小单标的示例，开仓一次并固定步数后平仓。
- [examples/02_single_symbol_sma.py](./examples/02_single_symbol_sma.py)：典型单标的双均线趋势跟随，使用 `on_bars(dt, bars)`。
- [examples/03_multi_symbol_rotation.py](./examples/03_multi_symbol_rotation.py)：典型多标的横截面动量轮动，使用 `on_bars(dt, bars)`。
- [examples/04_scenario_exit_rules.py](./examples/04_scenario_exit_rules.py)：真实场景订单附带止盈止损和追踪止损，提交订单时设置，持仓过程中可修改。
- [examples/05_scenario_limit_order.py](./examples/05_scenario_limit_order.py)：真实场景限价单，展示挂单、成交、订单级退出条件。
- [examples/06_scenario_single_breakout.py](./examples/06_scenario_single_breakout.py)：真实场景单标的趋势突破，包含波动过滤、目标仓位和策略内止损。
- [examples/07_scenario_multi_rotation.py](./examples/07_scenario_multi_rotation.py)：真实场景多标的横截面轮动，包含动量排序、等权目标仓位和定期再平衡。
- [examples/08_scenario_pairs_mean_reversion.py](./examples/08_scenario_pairs_mean_reversion.py)：真实场景双标的配对均值回归，包含 z-score 入场、双腿持仓和退出条件。
- [examples/example_utils.py](./examples/example_utils.py)：示例共用工具，包括静默 logger 和目标名义金额调仓辅助函数。
- [examples/data.csv](./examples/data.csv)：单标的 BTCUSDT 示例行情。

## 行情数据约定

推荐使用 `Exchange.set_bars(data, date_key="dt")` 接入 K 线或类似 bar 结构的数据。目标用户接口不再提供 `set_data(...)`。

`Exchange.set_bars(data, date_key="dt", symbol_key="symbol", price_key="close")` 支持三种输入：

- `pandas.DataFrame`
- `polars.DataFrame`
- `list[dict]`

`list[dict]` 会由 Exchange 原生迭代和排序，不依赖 polars 可用性。

必需字段：

- `dt`: 默认时间字段，可通过 `date_key` 改名。
- `symbol`: 标的代码。
- `close`: 当前 bar 的成交价格，市价单默认按该价格成交。

时间字段：

- 数据会按 `[date_key, symbol]` 排序。
- `(date_key, symbol)` 必须唯一；重复数据会在 `set_bars()` 阶段抛出 `ValueError`。
- Exchange 会按同一时间点聚合成 bar，先更新该时间点所有 symbol 的最新价，再触发策略。
- 单标的是多标的结构的特例，仍然使用 `on_bars(dt, bars)`。

除 K 线外，Exchange 还保留同一模型的数据入口：

- `set_books(data, date_key="dt", symbol_key="symbol", price_key=None)`
- `set_trades(data, date_key="dt", symbol_key="symbol", price_key="price")`
- `set_news(data, date_key="dt")`

同一 `dt` 下的回调顺序固定为 `on_bars -> on_books -> on_trades -> on_news`。

## 核心对象

### Exchange

`Exchange` 负责保存数据源、按时间截面广播数据、维护最新价格，并调度策略生命周期：

- `on_init()`: 回测开始前调用。
- `on_bars(dt, bars)`: 每个时间点调用一次，`bars` 是 `{symbol: row}` 形式的同一时间截面数据。
- `on_books(dt, books)`: orderbook 或类似盘口快照数据，`books` 是 `{symbol: row}`。
- `on_trades(dt, trades)`: 逐笔成交或类似明细数据，`trades` 是 `{symbol: [row, ...]}`。
- `on_news(dt, news)`: 新闻或事件数据，`news` 是 `[row, ...]`。
- `on_finish()`: 回测结束后调用。

如果多个策略共享同一个 `Broker`，Exchange 会按 broker 对象去重更新价格，避免同一 broker 被重复喂价。每个 `dt` 会先更新全部价格、处理限价挂单和退出条件，再触发策略回调。

### Strategy

用户通常继承 `Strategy` 并实现 `on_bars`。单标的是多标的 `bars` 结构的特例，因此单标的和多标的写法保持一致。策略可通过 `self.broker` 下单和查询账户状态：

```python
self.broker.submit_market_order("BTCUSDT", qty=1, price=100, leverage=3)
self.broker.submit_market_order("BTCUSDT", qty=-1, price=105)
self.broker.order_target_size("BTCUSDT", target_size=2, price=100)
self.broker.order_target_value("BTCUSDT", target_value=5_000, price=100)
self.broker.order_target_percent("BTCUSDT", target_percent=0.8, price=100)
self.broker.close_position("BTCUSDT", price=105)
self.broker.get_total_equity()
self.broker.get_position_size("BTCUSDT")
```

`qty > 0` 表示买入或做多，`qty < 0` 表示卖出或做空。反向下单会先平掉已有仓位，超出部分再开反向仓位。

`on_bars` 示例：

```python
def on_bars(self, dt, bars):
    btc = bars["BTCUSDT"]
    eth = bars["ETHUSDT"]
    if btc["close"] > eth["close"]:
        self.broker.submit_market_order("BTCUSDT", qty=1)
```

如果 `submit_market_order()` 不传 `price`，Broker 会使用 Exchange 在当前 bar 开始时写入的最新价；标的尚无最新价时抛出 `ValueError`，不会生成 rejected Order。

### Broker 和 Portfolio

`Broker` 管理一个或多个 portfolio。默认创建 `main` portfolio，`initial_cash` 默认全部进入 `main`：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001)
broker.add_portfolio("trend", cash=30_000)

broker.order_target_percent("BTCUSDT", 0.8, price=100, portfolio="trend")
```

权益查询语义：

- `broker.get_total_equity()`: 所有 portfolio 权益。
- `broker.get_equity(portfolio="main")`: 指定 portfolio 权益；默认返回 `main`。
- `broker.get_cash(portfolio="main")`: 指定 portfolio 可用现金。
- `broker.get_position(symbol, portfolio="main")`: 查询持仓；不存在时返回 `None`，不会创建空持仓。
- `broker.get_orders(portfolio=..., symbol=...)`: 按组合和标的筛选订单。

市场规则可以通过 `market` 参数扩展：

```python
from minbt import Broker, markets

crypto_broker = Broker(initial_cash=100_000, fee_rate=0.0005, market=markets.CRYPTO)
a_stock_broker = Broker(initial_cash=100_000, fee_rate=0.0003, market=markets.A_STOCK)
```

`markets.A_STOCK` 当前实现最小 A 股规则：交易时间、100 股一手、价格 tick、不可做空、T+1 持仓锁定。同日买入的持仓 `locked_size` 大于 0，`close_position()` 和 `close_portfolio()` 会在可平数量不足时失败，而不是静默部分平仓。直接调用 broker 下单时需要传入 `price_dt`；通过 Exchange 回测时，`date_key` 会自动传入。目标仓位接口产生的买入数量会按整手向 0 方向规范化。

### 订单级退出条件

推荐在提交订单或目标仓位调整时直接设置退出条件，数值表示触发价：

```python
def on_bars(self, dt, bars):
    price = bars["BTCUSDT"]["close"]

    if not self.entered:
        order = self.broker.order_target_percent(
            "BTCUSDT",
            target_percent=0.8,
            price=price,
            stop_loss_price=price * 0.95,
            take_profit_price=price * 1.10,
            trailing_stop_pct=0.05,
        )
        self.entry_order_id = order.id
        self.entered = True
```

持仓过程中可以按订单 ID 修改：

```python
self.broker.set_exit(
    self.entry_order_id,
    stop_loss_price=price * 0.98,
    take_profit_price=price * 1.12,
)
```

也可以清除部分或全部退出条件：

```python
self.broker.clear_exit(self.entry_order_id, trailing_stop=True)
```

退出条件会在每个策略回调前检查，触发后按当前最新价市价平仓。不模拟同一根 bar 内的高低价路径，也不是交易所真实挂单。

追踪止损规则：

- `trailing_stop_pct` 和 `trailing_stop_amount` 互斥。
- 固定止损/止盈可以和追踪止损同时存在。
- 多头追踪最高价，空头追踪最低价。

### 函数式退出规则

如果需要更复杂的退出条件，可以给订单追加函数式规则。常规止盈止损是函数式条件的特殊形式：

```python
def exit_if_breaks_support(ctx):
    return ctx.price < ctx.state["support"]

def on_bars(self, dt, bars):
    price = bars["BTCUSDT"]["close"]
    if not self.entered:
        order = self.broker.submit_market_order("BTCUSDT", qty=1, price=price)
        self.broker.add_exit(
            order.id,
            name="support_break",
            condition=exit_if_breaks_support,
            state={"support": price * 0.96},
        )
        self.entered = True
```

`ctx` 包含 `order_id/symbol/portfolio/dt/price/position/broker/data/state`。函数返回 `True` 时触发退出。

### 限价单

限价单按当前最新价触发，不根据 bar 的 high/low 推断路径：

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

买入限价单在最新价小于等于 `limit_price` 时成交，卖出限价单在最新价大于等于 `limit_price` 时成交。提交时会按当前账户状态预检资金，但 MVP 不为 pending 订单预留资金；触发时资金不足会将订单更新为 rejected，且不会产生部分成交。

## 资金和保证金模型

开仓时：

- 手续费为 `abs(qty) * price * fee_rate`。
- 保证金占用为 `abs(qty) * price / leverage`。
- 手续费从现金扣除，不计入持仓未实现盈亏。

逐仓模式：

- 每个 symbol 独立计算 `position.equity / position.margin`。
- 单个仓位触发穿仓或强平时，只影响该仓位。

全仓模式：

- 使用账户级权益计算保证金水平：`portfolio_equity / total_margin`。
- 可用现金会作为全仓风险缓冲。
- 账户穿仓时，该 portfolio 会被标记破产，现金和持仓归零。

## 日志

全局 logger 支持中英文消息：

```python
from minbt import logger

logger.set_lang("zh")
logger.info("[start_strategy]", "demo")
logger.info("on_bars", {"symbol": "BTCUSDT", "close": 100})
```

普通消息支持 `{}` 格式化；没有占位符但传入参数时，会追加参数文本，避免日志参数被静默丢弃。

## Codex Skill

仓库包含一个面向 Codex 的本地 skill：

```text
./skills/minbt-usage
```

在支持本地 skills 的 Codex 环境中，可以使用：

```text
Use $minbt-usage to build a minbt strategy for my CSV data.
```

该 skill 会提醒 Codex 遵循本项目的数据约定、保证金语义、测试命令和文档规范，适合生成策略、排查资金/仓位问题、补测试或更新示例。

## 测试

运行全量测试：

```bash
pytest -q
```

运行基础编译检查：

```bash
python -m compileall -q minbt tests examples
```

当前测试环境可能出现 `Polars binary is missing!` warning；这属于环境依赖警告，不影响现有测试通过。

## 设计约束和已知限制

- 已支持市价单、限价单、订单级止盈止损、追踪止损和函数式退出条件。
- 限价单和退出条件按当前最新价触发，不模拟 intrabar 路径。
- Exchange 不负责拉取或缓存历史行情，用户需要自行准备数据。
- 市价单在回测中按当前 `close` 成交，未模拟订单簿、滑点或部分成交。
- 多 symbol 数据必须具备 `date_key`；同一 `date_key` 的多标的会作为一个时间截面处理。
- 当前资金模型是保证金合约账户模型：`Position.equity` 表示保证金加未实现盈亏，不是现货市值。

## ChangeLog

- [@2026-06-24] v0.0.4：修复全仓保证金、总权益统计、日志参数和 Python 3.8 注解兼容问题。
- [@2024-11-16] v0.0.3 release。
