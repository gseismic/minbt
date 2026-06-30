---
name: minbt-usage
description: Use when building, reviewing, debugging, or documenting minbt backtests and strategies in this repository. Trigger for tasks involving Exchange, Strategy, Broker, Portfolio, Position, market orders, cross or isolated margin, portfolio equity, OHLCV data loading, examples, tests, README updates, or minbt usage guidance.
---

# minbt Usage

## 核心工作流

1. 修改行为前先读当前代码：`minbt/exchange.py`、`minbt/strategy.py`、`minbt/broker/broker.py`、`minbt/broker/portfolio.py`、`minbt/broker/struct.py`。
2. 写用户示例前先读 `README.md`、基础示例和真实场景示例。
3. 基础示例：`examples/01_demo_mini.py`、`examples/02_single_symbol_sma.py`、`examples/03_multi_symbol_rotation.py`。
4. 真实场景示例：`examples/04_scenario_exit_rules.py` 至 `examples/08_scenario_pairs_mean_reversion.py`。
5. 行为变更需要补聚焦测试，并运行相关测试和 `pytest -q`。
6. 遵守 `AGENTS.md`：实施类工作在 `docs/dev/PLAN-XXX-*.md` 和 `*-OUTCOME.md` 写中文计划与结果。

## 数据契约

- 推荐入口是 `Exchange.set_bars(data, date_key="dt")`，用户接口不提供 `set_data(...)`。
- `data` 支持 pandas DataFrame、polars DataFrame 或 `list[dict]`。
- bars 必需字段是 `dt`、`symbol` 和 `close`，字段名可通过参数调整。
- `list[dict]` 由 Exchange 原生迭代，不要假设 list 输入必须依赖 polars。
- `date_key` 和 `symbol_key` 必须存在，不支持用行号代替时间。
- bars 和 books 的 `(date_key, symbol_key)` 必须唯一。
- trades 同一时间和标的可以包含多条记录，news 同一时间可以包含多条记录。
- `Exchange.run()` 按 `on_bars -> on_books -> on_trades -> on_news` 调度。
- 每个 dt 内先整体更新价格，再处理 pending 订单和退出条件，最后调用策略回调。
- 如果多个策略共享同一个 Broker，Exchange 每个 bar 只更新该 Broker 一次价格。

## 策略写法

Strategy 用户回调只有 `on_init/on_bars/on_books/on_trades/on_news/on_finish`。单标的是多标的结构特例，交易统一通过 `self.broker`，不要添加 Strategy 交易语法糖。

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

## Broker 语义

- `Broker(initial_cash, fee_rate, leverage=1.0, margin_mode="cross")` 创建 `main` 并放入全部初始现金。
- `broker.add_portfolio(name, cash)` 从 `main` 可用现金划拨资金。
- `broker.submit_market_order(symbol, qty, price=None, *, leverage=None, price_dt=None, portfolio=None, ...)` 返回 Order。
- `price=None` 使用最新价；没有最新价时抛 `ValueError`，不创建订单。
- `order_target_size/value/percent(...)` 分别调整目标净持仓、目标名义金额和目标权益比例。
- `close_position(...)` 全平指定持仓；空仓返回 skipped，市场规则拒绝时返回 rejected。
- `close_portfolio(portfolio)` 原子关闭组合；任一仓位不能关闭时不执行任何成交。
- `submit_limit_order(...)` 提交 pending 限价单，提交和触发时均检查资金。
- `cancel_order(order_id)` 成功撤单会更新原挂单并返回取消动作；terminal 订单原样返回。
- `get_orders(portfolio=..., symbol=...)` 支持筛选。
- `get_position(symbol, portfolio=None)` 不创建空持仓。
- `qty > 0` 表示买入，`qty < 0` 表示卖出；`size` 只表示当前净持仓。

## 市场与退出规则

- 推荐使用 `Market(...)` 和 `markets.DEFAULT/CRYPTO/A_STOCK` 表达市场特征。
- `markets.CRYPTO` 是加密资产预设。
- `markets.A_STOCK` 是最小 A 股预设，包含交易时间、100 股一手、价格 tick、不可做空和 T+1 持仓锁定；直接调用 broker 时必须传 `price_dt`，目标仓位买入数量会按整手向 0 方向规范化。
- 不存在 `MarketModel/SimpleMarket/CryptoMarket/ChinaAStockMarket` 兼容入口。
- `Position.available_size` 和 `Position.locked_size` 是 broker 内部状态，用于 T+1 等市场规则，不作为用户初始化主路径。
- 推荐在提交订单或目标仓位时用 `stop_loss_price/take_profit_price` 设置固定退出价。
- `trailing_stop_pct` 和 `trailing_stop_amount` 互斥。
- 中途修改使用 `set_exit(order_id, ...)`，清除使用 `clear_exit(order_id, ...)`。
- 自定义退出使用 `add_exit(order_id, name=..., condition=..., state=...)`。
- `state` 可以是字典或返回字典的工厂；工厂只调用一次，状态在多个 dt 之间持久化。
- Order 只有在仍属于当前净持仓生命周期时才能新增或修改退出规则。

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
pytest -q tests/test_api_contract.py
pytest -q tests/test_exchange.py tests/test_strategy.py tests/test_broker.py
pytest -q tests/test_portfolio.py tests/test_portfolio2.py tests/test_position.py
pytest -q tests/test_logger.py tests/test_examples.py
python examples/06_scenario_single_breakout.py
python examples/07_scenario_multi_rotation.py
python examples/08_scenario_pairs_mean_reversion.py
pytest -q
python -m compileall -q minbt tests examples
git diff --check
```

当前环境可能出现 `Polars binary is missing!` warning；只要测试未失败，就按环境依赖警告处理。

## 文档更新

- 用户文档保持中文。
- README 示例优先展示可直接运行的内存数据片段。
- 新示例只展示 `set_bars/on_bars` 和 `self.broker` 交易。
- 当前限制必须写清楚：不模拟入场 stop order、滑点、订单簿队列、部分成交和 intrabar 路径。
- 限价单、订单附带固定退出价、追踪止损和函数式退出规则已经实现。
