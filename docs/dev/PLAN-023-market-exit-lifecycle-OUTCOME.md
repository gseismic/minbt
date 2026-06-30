# PLAN-023 市场与退出生命周期 - 结果

## 真实性复核

计划中的问题均确认真实存在：

1. T+1 锁定多头可通过跨零卖出反手为空头。
2. 已平仓旧订单可错误绑定同标的重新开立的新持仓。
3. 新退出配置覆盖旧配置时，旧配置仍可能显示 active。
4. callable state 每次检查都会重新创建字典。
5. `ExitConfig` 缺少设计字段并暴露内部可变规则对象。

## 已完成

1. 所有反向订单按实际平仓部分检查 `available_size`。
2. 跨零反手不能绕过 T+1 锁定。
3. Broker 按 portfolio 和 symbol 跟踪当前持仓生命周期内的有效订单。
4. 同方向调整保留当前生命周期；全平或反手使旧订单失效。
5. `set_exit()` 和 `add_exit()` 拒绝不属于当前持仓生命周期的订单。
6. 新退出配置覆盖当前持仓时，旧配置同步标记为 inactive。
7. callable state 在添加规则时只初始化一次。
8. 内部 `_ExitState` 保存运行期规则，公开 `ExitConfig` 作为快照返回。
9. `ExitConfig` 增加 `symbol/portfolio`，`custom_rules` 返回规则名元组。
10. 外部修改 `ExitConfig` 不会改变 Broker 内部退出状态。

## 测试覆盖

1. T+1 锁定多头跨零反手被拒绝。
2. 空头反手为多头只锁定新增多头净额。
3. 平仓重开后旧订单无法控制新持仓。
4. 同方向减仓订单仍属于当前生命周期，反手后统一失效。
5. 新退出配置会停用旧退出配置。
6. callable state 跨多个 dt 持久化并按预期触发。
7. 公开 ExitConfig 字段、规则名和快照隔离正确。

## 验证

```text
pytest -q tests/test_broker.py
40 passed

pytest -q
112 passed
```

## 结论

`PLAN-023` 的核心行为目标已经完成。多批次持仓独立退出条件仍不进入当前 MVP。

`PLAN-024-api-contract-conformance.md` 的代码收敛已完成一部分，但 README、usage skill、设计现状描述和完整签名快照测试尚未实施，本阶段不宣称该计划完成。
