# PLAN-016 exit-rule-example

## 背景

需要一个带止盈止损的真实用户接口示例，用来评估当前 API 是否简洁、是否贴近“策略中调用 broker 实现交易”的目标。

当前已有函数式退出规则：

- `broker.add_exit_rule(symbol, stop_loss_pct(...))`
- `broker.add_exit_rule(symbol, take_profit_pct(...))`

但这更像内部或高级接口。真实交易场景里，用户更常见的心智模型是：

1. 提交订单时同时设置止盈止损。
2. 持仓过程中可以修改止盈止损。
3. 策略仍然只通过 broker 交易，不引入 Strategy DSL。

## 目标

1. 支持在 `submit_market_order` 和目标仓位接口中传入 `stop_loss`、`take_profit`。
2. 支持通过 `broker.set_exit(symbol, stop_loss=..., take_profit=...)` 修改持仓止盈止损。
3. 支持通过 `broker.clear_exit(symbol)` 清除订单附带的止盈止损。
4. 保留 `broker.add_exit_rule(...)` 作为函数式高级接口。
5. 新增一个可运行示例，展示提交订单时设置止盈止损、持仓中途修改止损。
6. 示例使用 `on_bars(dt, bars)` 和 `self.broker`，不引入额外 DSL。
7. 示例加入 examples 测试，避免后续接口变更破坏用户示例。
8. 更新 README 示例列表。

## 非目标

1. 不实现挂单式止损。
2. 不实现限价单。
3. 不模拟 bar 内高低价路径。
4. 不引入复杂的订单状态机。
5. 不把止盈止损设计成真实交易所挂单；当前仍是 bar 级回测触发。

## 验收标准

1. `python examples/scenario_exit_rules.py` 可运行。
2. 输出包含 `final_equity=`。
3. 示例代码中交易入口仍然是 `self.broker`。
4. 示例中止盈止损在下单时设置。
5. 示例中止损可以中途修改。
6. 全量测试通过。
