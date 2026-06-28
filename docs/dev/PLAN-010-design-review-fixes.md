# PLAN-010 设计 review 修复

## 背景

对当前设计稿 review 后发现若干会影响后续实现的契约问题：

1. `initial_cash` 与初始持仓权益、保证金的关系不够明确。
2. `close_position` 在 T+1 场景下允许“部分平或拒绝”，用户语义不够安全。
3. `MarketModel` 需要按市场特征定义，而不是硬编码 A 股或加密市场。
4. `add_exit_rule` 示例不一致。
5. 函数式退出规则的触发顺序与 ATR 示例存在状态时序冲突。
6. 两份设计稿的 MVP 顺序不一致。

用户明确确认：

- `initial_cash` 应代表初始现金。
- T+1 应通过市场规则检查是否同一交易日。
- 市场应定义可交易时间、T+1、最小交易手等特征。
- 加密市场的最小交易单元可能按 symbol 不同，可以后期追加。

## 目标

1. 明确 `initial_cash` 是初始现金，不是初始总权益。
2. 明确初始持仓默认 `leverage=1.0`，并定义 `margin/leverage` 规则。
3. 明确 `close_position` 默认全平语义，T+1 下不能全平时返回失败。
4. 把 `MarketModel` 改成市场特征组合，覆盖交易时间、交易日、T+0/T+1、lot size、tick size、是否允许做空等。
5. 明确 symbol 级最小交易单元是后续扩展点。
6. 固化 `add_exit_rule` 推荐签名。
7. 明确退出规则使用当前价格和上一轮策略状态。
8. 在设计索引中统一全局实施顺序。

## 不做

1. 不修改代码。
2. 不修改 README。
3. 不修改 examples。
4. 不实现任何新接口。

## 验证

1. 检查设计稿中 `initial_cash` 语义一致。
2. 检查 `close_position` 不再允许静默部分平仓。
3. 检查 `MarketModel` 包含交易时间和交易日语义。
4. 检查 `add_exit_rule` 有唯一推荐签名。
5. 运行 `git diff --check`。

