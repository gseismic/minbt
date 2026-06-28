# PLAN-013 修复设计实施后的 review 问题结果

## 结果

已修复本轮 review 中确认正确的问题。

## 已修复

1. `Broker.close_portfolio()` 不再直接调用 `Portfolio.close_all_positions()`，改为先预校验待平仓订单，再通过 broker 层 `close_position()` 执行，避免绕过 `MarketModel`。
2. 市价订单入口接入 `MarketModel.normalize_order_qty()`。
3. `ChinaAStockMarket` 的目标买入数量按 100 股整手向 0 方向规范化。
4. `ChinaAStockMarket` 在缺少 `dt` 时拒绝交易，避免直接调用 broker 时静默跳过交易时间校验。
5. `BrokerProtocol` 错误提示列出完整必需方法，包含目标仓位接口和 `close_position`。
6. README、设计文档和本地 skill 已同步市场规则说明。

## 测试覆盖

新增或更新测试覆盖：

1. A 股手动下单未传 `price_dt` 时拒单。
2. A 股目标金额下单按整手规范化。
3. `close_portfolio()` 遵守 T+1 锁仓规则。
4. `close_portfolio()` 关闭失败时不移除 portfolio。
5. 自定义 broker 缺目标仓位方法时，错误信息包含完整方法名。

## 验证

已运行：

```bash
pytest -q tests/test_design_mvp.py tests/test_broker.py::test_close_portfolio_keeps_portfolio_when_close_fails tests/test_strategy.py::test_strategy_broker_protocol_error_lists_target_methods
pytest -q
python -m compileall -q minbt tests examples
git diff --check
```

结果：

- 定向测试：10 passed。
- 全量测试：81 passed。
- 编译检查通过。
- `git diff --check` 通过。
