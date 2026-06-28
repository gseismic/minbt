# PLAN-012 实施当前 MVP 设计结果

## 结果

已完成当前 MVP 设计实施。

## 已实现

1. 新增 `Exchange.set_bars(data, date_key=None)` 作为推荐 bars 数据入口。
2. 新增 `Strategy.on_bars(dt, bars)`，并让 `Exchange.run()` 优先调用该接口。
3. 保留 `on_data(row)` 和 `on_bar(dt, rows_by_symbol)` 兼容路径。
4. Exchange 在每个时间截面先更新全部 symbol 最新价，再检查 broker 退出规则，再调用策略。
5. 新增 `Broker.order_target_size(...)`、`order_target_value(...)`、`order_target_percent(...)`。
6. 新增 `Broker.close_position(...)`，在市场规则不允许全部平仓时返回失败。
7. 新增 `MarketModel`、`SimpleMarket`、`CryptoMarket`、`ChinaAStockMarket`。
8. 新增 `Position.available_size` 和 `Position.locked_size`，用于 T+1 等市场规则。
9. `ChinaAStockMarket` 支持最小交易时间、100 股一手、tick size、不可做空和当日买入锁定。
10. 新增函数式退出规则：`broker.add_exit_rule(...)`、`clear_exit_rules(...)`、`stop_loss_pct(...)`、`take_profit_pct(...)`。
11. 更新 README、设计文档和本地 skill，用户主路径统一为 `set_bars/on_bars + self.broker`。
12. 更新基础示例和真实场景示例，单标的和多标的都使用 `on_bars(dt, bars)`。

## 未实现

1. 未实现 `Broker(initial_positions=...)`，继续保持从现金开始的 MVP。
2. 未实现 `on_books/on_trades/on_news`，保留为未来扩展方向。
3. 未实现限价单、挂单式止损、追踪止损和复杂订单状态机。
4. 未实现滑点、订单簿撮合、部分成交和 intrabar 高低价路径推断。
5. 未实现每个 symbol 独立最小交易单元等更细市场规则。

## 关键修正

`order_target_percent(..., price=...)` 会先用显式价格刷新 broker 权益，再计算目标权重，避免手动调用时使用旧价格权益。

## 验证

已运行：

```bash
pytest -q tests/test_design_mvp.py
pytest -q tests/test_examples.py
pytest -q tests/test_exchange.py tests/test_strategy.py tests/test_broker.py
pytest -q
python -m compileall -q minbt tests examples
git diff --check
```

结果：

- `tests/test_design_mvp.py`：5 passed。
- `tests/test_examples.py`：6 passed。
- `tests/test_exchange.py tests/test_strategy.py tests/test_broker.py`：23 passed。
- 全量测试：77 passed。
- 编译检查通过。
- `git diff --check` 通过。
