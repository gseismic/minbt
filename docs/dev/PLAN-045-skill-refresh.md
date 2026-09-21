# PLAN-045：同步 minbt 使用技能契约

## 目标

检查 `./skills` 下的用户技能，使 `skills/minbt-usage` 与当前源码、README、示例和公开测试契约一致，
让 Agent 能在用户策略任务中正确选择数据入口、订单接口和验证方式。

## 实施范围

1. 收紧 `SKILL.md` 的触发描述，明确面向用户策略/回测，不覆盖 minbt 内部实现。
2. 补充当前已实现但技能缺少的公开语义：多事件回调顺序、`run(streaming=...)` 选择、CSV/iosql
   半开区间与 fail-fast、订单状态和限价单边界、净盈亏计算与专项验证。
3. 更新 `agents/openai.yaml` 的 UI 描述和默认提示，使其覆盖本地 bars、数据 Feed 与验证场景。
4. 使用 skill validator、项目测试、编译检查和 diff 检查验证更新，不新增不必要的辅助资源。

## 验收标准

- `quick_validate.py skills/minbt-usage` 通过。
- 技能中的示例、方法名、参数名和行为说明与当前实现一致。
- 相关测试、编译检查和 `git diff --check` 通过。
- 生成 `PLAN-045-skill-refresh-OUTCOME.md`，记录审查结论与验证结果。

## 边界

本计划只更新 `./skills` 及其开发记录，不修改 minbt 运行时代码，也不覆盖工作区中已有的其他未提交变更。
