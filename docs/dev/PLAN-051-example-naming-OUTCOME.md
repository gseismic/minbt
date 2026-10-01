# PLAN-051 示例文件分级编号命名结果

## 结果

已按 [PLAN-051](PLAN-051-example-naming.md) 和分级编号命名规范完成 `examples/` 中 16 个可运行示例的改名。大类编号与类别标识对应为：`0/core`、`1/scenario`、`2/benchmark`、`3/feed`、`4/exchange`；各类序号从 `00` 开始递增。

示例命令和链接已同步更新到 README 与 `skills/minbt-usage/SKILL.md`；测试中的脚本路径和动态模块名、示例截图输出名，以及仍在使用的设计文档和 HANDOFF 路径也已更新。`examples/screenshots/` 中已有的忽略截图同步改为新名称。共用工具、数据文件、v0 归档和历史计划/Review 文档保留原名。

## Review

- 对照 Git 中的原始版本检查了全部 16 个脚本；内容变化仅限于匹配新文件名的截图输出名。
- 在 README、skills、HANDOFF、tests、docs/design 和 examples 中检索旧示例路径，没有发现残留引用。
- `git diff --check` 通过。
- 未运行测试。
