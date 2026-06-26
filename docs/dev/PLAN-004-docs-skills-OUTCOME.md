# PLAN-004-docs-skills-OUTCOME

## 实施结果
- 重写 `README.md`，补充项目定位、功能清单、安装方式、快速开始、行情数据约定、核心对象、资金和保证金模型、日志、Codex skill、测试命令、设计约束和 ChangeLog。
- 新增 `skills/minbt-usage/SKILL.md`，用于指导 Codex 在本仓库中构建、审查、调试和文档化 minbt 回测。
- 新增 `skills/minbt-usage/agents/openai.yaml`，提供 skill 的 UI 元数据和默认提示词。
- 新增 `docs/dev/PLAN-004-docs-skills.md` 记录实施计划。

## 验证结果
- `python /Users/mac/.codex-8/skills/.system/skill-creator/scripts/quick_validate.py skills/minbt-usage`: Skill is valid。
- `pytest -q`: 49 passed，1 warning。
- `git diff --check`: 通过。

## 说明
- `skills/minbt-usage` 是仓库内本地 skill，方便用户在支持本地 skills 的 Codex 环境中通过 `$minbt-usage` 使用 minbt 项目约定。
- 测试环境仍有 `Polars binary is missing!` warning，本轮未处理该环境依赖提示。
