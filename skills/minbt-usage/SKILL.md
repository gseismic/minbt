---
name: minbt-usage
description: Use when helping a user build, adapt, review, or debug a minbt trading strategy or backtest. Trigger for tasks involving user strategy code, local OHLCV/bar data, Exchange.set_bars, Strategy.on_bars, Broker orders, target positions, exits, limit orders, portfolios, markets, examples, or README usage guidance.
---

# minbt Usage

本 skill 面向“用户使用 minbt 写策略”，不是内部框架开发文档。默认目标是用最少代码完成一个可运行、可验证的回测。

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

## 策略开发工作流

1. 先确认用户数据结构：时间列、标的列、价格列。
2. 优先使用 `Exchange.set_bars(data, date_key="dt", symbol_key="symbol", price_key="close")`。
3. 继承 `Strategy`，在 `on_init()` 初始化状态。
4. 在 `on_bars(dt, bars)` 读取当前时间截面。
5. 只通过 `self.broker` 下单和查询状态。
6. 用 `Order.status` 判断下单结果，不依赖 `reason` 精确文本。
7. 给用户提供最小运行命令和验证命令。

如果用户要求写示例，优先参考：

- `examples/01_demo_mini.py`: 最小单标的。
- `examples/02_single_symbol_sma.py`: 单标的均线。
- `examples/03_multi_symbol_rotation.py`: 多标的横截面轮动。
- `examples/04_scenario_exit_rules.py`: 订单级退出条件。
- `examples/05_scenario_limit_order.py`: 限价单。
- `examples/06_scenario_single_breakout.py`: 单标的真实场景。
- `examples/07_scenario_multi_rotation.py`: 多标的轮动。
- `examples/08_scenario_pairs_mean_reversion.py`: 配对均值回归。
- `examples/09_benchmark_100k_empty.py`: 10 万行空策略基准。
- `examples/10_scenario_cross_market.py`: 一个 Broker 内同时交易 A 股和 crypto。

## 数据契约

推荐 bars 数据至少包含：

```text
dt, symbol, close
```

规则：

- `data` 可以是 pandas DataFrame、polars DataFrame 或 `list[dict]`。
- 单标的也是多标的的特例，仍建议保留 `symbol` 列。
- 同一 `(dt, symbol)` 只能有一条 bar。
- Exchange 会先更新同一 `dt` 下全部 symbol 的最新价，再触发策略回调。
- 不要使用行号代替时间；`date_key` 必须存在。

如果用户数据列名不同，映射参数即可：

```python
exchange.set_bars(data, date_key="date", symbol_key="ticker", price_key="close_price")
```

如果用户只有单标的 CSV 且缺少 `symbol` 列，可以在加载后补一列：

```python
data["symbol"] = "BTCUSDT"
exchange.set_bars(data, date_key="date", symbol_key="symbol", price_key="close")
```

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
```

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
python examples/01_demo_mini.py
pytest -q tests/test_examples.py
pytest -q
python -m compileall -q minbt tests examples
git diff --check
```

如果只写了新的独立策略脚本，至少运行该脚本和 `python -m compileall -q`。

当前环境可能出现 `Polars binary is missing!` warning；只要测试未失败，就按环境依赖警告处理。

## 文档更新原则

- README 和示例优先面向用户写策略，不讲内部状态机。
- 简单路径短，复杂功能渐进展开。
- 不恢复 `on_data/on_bar/on_tick/set_data` 旧入口。
- 不在 Strategy 上添加交易语法糖；交易统一通过 `self.broker`。
- 限价单、固定退出价、追踪止损和函数式退出已经实现，文档不要写成未实现。
