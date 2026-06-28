# PLAN-011 移除 initial_positions 主路径设计

## 背景

继续 review Broker 初始状态设计后，确认 `initial_positions` 会引入不必要复杂度：

- 成本价语义。
- 现货和保证金持仓差异。
- 杠杆与保证金字段。
- 可用数量与锁定数量。
- 持仓批次和 T+1 判断。

minbt 的目标是最简快捷回测，重心是策略。大多数回测从现金开始，不需要从已有持仓继续。

## 目标

1. 从当前 MVP 和推荐用户接口中移除 `Broker(initial_positions=...)`。
2. 明确 `Broker` 主路径只从 `initial_cash` 开始。
3. 保留 `available_size/locked_size` 作为 broker 内部状态，而不是用户初始化字段。
4. 将已有持仓账户快照列为明确不进入当前 MVP。
5. 更新典型场景，避免示例继续展示已有持仓初始化。

## 不做

1. 不修改代码。
2. 不修改 README。
3. 不修改 examples。
4. 不删除未来账户快照的可能性，只是不作为当前主路径。

## 验证

1. 检查 `initial_positions` 不再出现在推荐接口和实施顺序中。
2. 检查典型示例均从现金开始。
3. 运行 `git diff --check`。

