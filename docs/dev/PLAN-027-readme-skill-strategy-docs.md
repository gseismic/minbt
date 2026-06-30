# PLAN-027 README 与策略开发 Skill 更新

## 目标

将 README 和 `./skills/minbt-usage` 更新为面向用户策略开发的文档，突出 minbt 的最简回测主路径：准备数据、实现 Strategy 回调、在策略中调用 broker 下单、查看结果。

## 范围

1. 更新 `README.md`：
   - 保留安装、快速开始、示例索引和测试命令。
   - 强化用户写策略需要理解的数据契约、策略回调、broker 交易接口、退出条件、限价单、分仓和市场规则。
   - 弱化或移除非核心内容，例如 logger 作为 README 主章节。
   - 明确当前边界：不模拟滑点、订单簿队列、部分成交和 intrabar 路径。
2. 更新 `skills/minbt-usage/SKILL.md`：
   - 由内部代码维护说明改为用户策略开发说明。
   - 明确 Agent 生成策略时的默认工作流、数据要求、策略模板、交易接口和验证方式。
   - 不鼓励直接使用内部对象或运行时钩子。
3. 如有必要，更新 `skills/minbt-usage/agents/openai.yaml` 的描述，让 skill 名义与用户策略开发一致。
4. 同步修正明显过期的文档索引，避免与 README 和 skill 冲突。

## 验证

- 运行 README 中的最小示例。
- 运行示例测试和全量测试。
- 检查 README 与 skill 不再推荐旧接口或内部接口。
- 执行 `git diff --check`。

## 非目标

- 不修改 minbt 运行时代码。
- 不新增策略 API。
- 不扩展交易所撮合能力。
