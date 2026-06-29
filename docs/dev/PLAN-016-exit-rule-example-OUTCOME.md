# PLAN-016 exit-rule-example 结果

## 实施结果

完成。

本次根据真实交易场景调整止盈止损用户接口：不再把 `add_exit_rule(...)` 作为常规止盈止损主路径，而是支持在提交订单或目标仓位调整时设置止盈止损，并允许持仓过程中修改。

## 新用户接口

下单时设置：

```python
self.broker.order_target_percent(
    "BTCUSDT",
    target_percent=0.8,
    price=price,
    stop_loss=price * 0.95,
    take_profit=price * 1.10,
)
```

中途修改：

```python
self.broker.set_exit(
    "BTCUSDT",
    stop_loss=price * 0.98,
    take_profit=price * 1.12,
)
```

清除订单附带退出条件：

```python
self.broker.clear_exit("BTCUSDT")
```

## 实现内容

1. `submit_market_order(...)` 支持 `stop_loss` 和 `take_profit`。
2. `order_target_size/value/percent(...)` 支持 `stop_loss` 和 `take_profit`。
3. 新增 `broker.set_exit(...)`，用于设置或修改订单附带止盈止损。
4. 新增 `broker.clear_exit(...)`，用于清除订单附带止盈止损。
5. 新增 `stop_loss_price(...)` 和 `take_profit_price(...)`。
6. `ExitRule` 增加 `attached` 标记，用于区分订单附带退出条件和 `add_exit_rule(...)` 添加的持久函数式规则。
7. 附带退出条件触发后，会清除同一 symbol 的附带退出条件，但不影响持久函数式规则。
8. 新增 `examples/scenario_exit_rules.py`，展示：
   - 提交订单时设置止盈止损。
   - 一个标的触发止盈。
   - 一个标的中途上移止损后触发止损。
9. 更新 README、设计文档、usage skill 和示例测试。

## 边界说明

1. 当前是 bar 级回测触发，不是交易所真实挂单。
2. 退出条件在每个 `on_bars` 前检查。
3. 触发后按当前 `close` 市价平仓。
4. 不模拟同一根 bar 内的 high/low 路径。
5. 不实现 pending stop order、追踪止损订单或订单状态机。
6. 更复杂的函数式退出条件仍使用 `add_exit_rule(...)`。

## Review 结论

发现并修复：

1. `clear_exit(...)` 原本没有校验 portfolio 是否存在，可能在内部退出规则表中创建无效 portfolio 键；已补 `_require_portfolio(...)`。

未发现其他需要继续修复的确定性缺陷。

## 验证结果

已通过：

```bash
python examples/scenario_exit_rules.py
pytest tests/test_design_mvp.py tests/test_examples.py tests/test_strategy.py -q
pytest -q
python -m compileall -q minbt tests examples
git diff --check
```

结果：

- `python examples/scenario_exit_rules.py` 输出 `final_equity=10600.00`。
- 聚焦测试 `25 passed`。
- 全量测试 `92 passed`。
- compileall 无错误。
- diff check 无错误。
