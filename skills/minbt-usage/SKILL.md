---
name: minbt-usage
description: Use when building, reviewing, debugging, or documenting minbt backtests and strategies in this repository. Trigger for tasks involving Exchange, Strategy, Broker, Portfolio, Position, market orders, cross or isolated margin, portfolio equity, OHLCV data loading, examples, tests, README updates, or minbt usage guidance.
---

# minbt Usage

## 核心工作流

1. 修改行为前先读当前代码：`minbt/exchange.py`、`minbt/strategy.py`、`minbt/broker/broker.py`、`minbt/broker/portfolio.py`、`minbt/broker/struct.py`。
2. 写用户示例前先读 `README.md`、基础示例和真实场景示例。
3. 基础示例：`examples/demo_mini.py`、`examples/single_symbol_sma.py`、`examples/multi_symbol_rotation.py`。
4. 真实场景示例：`examples/scenario_single_breakout.py`、`examples/scenario_multi_rotation.py`、`examples/scenario_pairs_mean_reversion.py`。
5. 行为变更需要补聚焦测试，并运行相关测试和 `pytest -q`。
6. 遵守 `AGENTS.md`：实施类工作在 `docs/dev/PLAN-XXX-*.md` 和 `*-OUTCOME.md` 写中文计划与结果。

## 数据契约

- 推荐入口是 `Exchange.set_bars(data, date_key=None)`；`Exchange.set_data(...)` 只作为兼容旧代码的 bars 入口。
- `data` 支持 pandas DataFrame、polars DataFrame 或 `list[dict]`。
- 必需字段是 `symbol` 和 `close`。
- `list[dict]` 由 Exchange 原生迭代，不要假设 list 输入必须依赖 polars。
- 如果提供 `date_key`，数据按 `[date_key, symbol]` 排序。
- 如果提供 `date_key`，`(date_key, symbol)` 必须唯一；同一 bar 内重复 symbol 应在 `set_bars()` 阶段失败。
- 如果省略 `date_key`，数据只能包含一个 symbol，并使用输入行号作为时间键；不要依赖 pandas DataFrame index。
- `Exchange.run()` 会把同一 `date_key` 的行聚合为一个 bar。
- 每个 bar 内，Exchange 和 Broker 会先更新全部 symbol 的价格，再调用 `Strategy.on_bars(dt, bars)`。
- 如果多个策略共享同一个 Broker，Exchange 每个 bar 只更新该 Broker 一次价格。

## 策略写法

示例和 README 只推荐 `on_bars(dt, bars)`。单标的是多标的结构的特例，不再展示 `on_data(row)` 作为主路径。

```python
from minbt import Broker, Exchange, Strategy


class MyStrategy(Strategy):
    def on_init(self):
        self.count = 0

    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["close"]
        if self.count == 0:
            self.broker.order_target_percent("BTCUSDT", 0.8, price=price)
        self.count += 1

    def on_finish(self):
        print(self.broker.get_total_equity())
```

多标的横截面逻辑直接遍历同一时间截面：

```python
class CrossSectionStrategy(Strategy):
    def on_bars(self, dt, bars):
        btc = bars["BTCUSDT"]
        eth = bars["ETHUSDT"]
        if btc["close"] > eth["close"]:
            self.broker.submit_market_order("BTCUSDT", qty=1)
```

兼容说明：旧的 `on_data(row)` 和 `on_bar(dt, rows_by_symbol)` 仍可用于旧测试或旧项目，但不要在新示例中推荐。

## Broker 语义

- `Broker(initial_cash, fee_rate, portfolio_cash=None, leverage=1.0, margin_mode="cross")` creates a default portfolio.
- `Broker(..., logger=custom_logger)` can be used to silence or redirect Portfolio order logs.
- `broker.add_sub_portfolio(id, initial_cash)` allocates cash from `remaining_free_cash`.
- `broker.get_total_equity()` returns all portfolio equity plus unallocated cash.
- `broker.get_all_portfolio_equity()` excludes unallocated cash.
- `broker.get_equity(portfolio_id=None)` returns one portfolio, defaulting to the main portfolio.
- `broker.submit_market_order(symbol, qty, price=None, leverage=None, portfolio_id="default")` uses the last known price when `price` is omitted.
- `broker.order_target_size(symbol, target_size, price=None, ...)` adjusts to a target position size.
- `broker.order_target_value(symbol, target_value, price=None, ...)` adjusts to a target notional value.
- `broker.order_target_percent(symbol, target_percent, price=None, ...)` adjusts to a target portfolio equity percentage.
- `broker.close_position(symbol, price=None, ...)` closes the whole current position and fails if market rules disallow the full close.
- Use `qty > 0` for buy or long exposure and `qty < 0` for sell or short exposure.
- `size` means current position; `qty` means order delta; do not mix these names.

## 市场与退出规则

- `SimpleMarket` 是默认 T+0 行为。
- `CryptoMarket` 是加密资产预设，可配置最小数量、最小名义金额、价格 tick 和是否允许做空。
- `ChinaAStockMarket` 是最小 A 股预设，包含交易时间、100 股一手、价格 tick、不可做空和 T+1 持仓锁定。
- `Position.available_size` 和 `Position.locked_size` 是 broker 内部状态，用于 T+1 等市场规则，不作为用户初始化主路径。
- `broker.add_exit_rule(symbol, stop_loss_pct(...))` 和 `take_profit_pct(...)` 可用于常规止盈止损。
- 自定义退出规则使用 `condition(ctx) -> bool`；规则在每个 `on_bars` 前检查，触发后通过当前 `close` 市价平仓。

## 保证金语义

- Fee is `abs(qty) * price * fee_rate`.
- Required margin is `abs(qty) * price / leverage`.
- Isolated margin checks each position's `equity / margin`.
- Cross margin checks account-level `portfolio_equity / total_margin`; free cash is part of the risk buffer.
- Cross bankruptcy zeroes that portfolio's cash and clears positions.

## 测试与验证

先跑聚焦测试，再跑全量验证：

```bash
pytest -q tests/test_design_mvp.py
pytest -q tests/test_exchange.py tests/test_strategy.py tests/test_broker.py
pytest -q tests/test_portfolio.py tests/test_portfolio2.py tests/test_position.py
pytest -q tests/test_logger.py tests/test_examples.py
python examples/scenario_single_breakout.py
python examples/scenario_multi_rotation.py
python examples/scenario_pairs_mean_reversion.py
pytest -q
python -m compileall -q minbt tests examples
git diff --check
```

当前环境可能出现 `Polars binary is missing!` warning；只要测试未失败，就按环境依赖警告处理。

## 文档更新

- 用户文档保持中文。
- README 示例优先展示可直接运行的内存数据片段。
- 新示例只展示 `set_bars/on_bars` 和 `self.broker` 交易。
- 当前限制必须写清楚：限价单、挂单式止损、追踪止损、滑点、订单簿撮合和部分成交未实现。
- 函数式退出规则已实现，不要再笼统写“止盈止损未实现”；应区分函数式退出规则和挂单式止损。
