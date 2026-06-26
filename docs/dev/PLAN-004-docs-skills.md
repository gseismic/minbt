# PLAN-004-docs-skills

## 目标
更新 README，让用户可以快速理解 minbt 的定位、安装方式、数据格式、基础回测流程、资金/保证金语义和测试方式；同时在仓库根目录生成 `./skills`，方便用户让 Codex 按项目约定使用 minbt。

## 实施范围
- `README.md`: 补充安装、快速开始、数据约定、核心对象、保证金模型、多组合、日志、测试和已知限制。
- `skills/minbt-usage/SKILL.md`: 生成面向 Codex 的 minbt 使用 skill。
- `skills/minbt-usage/agents/openai.yaml`: 生成 skill 的 UI 元数据。
- `docs/dev/PLAN-004-docs-skills-OUTCOME.md`: 记录结果和验证。

## 验证方式
- 运行 skill 校验脚本检查 `skills/minbt-usage` 元数据。
- 运行 `pytest -q` 确认文档和 skill 变更未破坏现有代码。
- 执行 `git diff --check`。
