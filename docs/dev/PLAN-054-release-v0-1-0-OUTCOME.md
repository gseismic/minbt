# PLAN-054：发布 v0.1.0 结果

## 状态

已完成文档与版本更新。发布提交完成后创建并核验 `v0.1.0` annotated tag。

## 变更

- 将 `pyproject.toml` 包版本更新为 `0.1.0`。
- README ChangeLog 增加 `v0.1.0` 发布条目，并记录数字时间戳、Binance 收盘 K 线、限价单触发、退出条件继承、持仓查询快照及 Market 时区/交易单位规则。
- `skills/minbt-usage/SKILL.md` 同步新增上述当前实现的使用契约。
- 本次只变更版本和文档，没有改动运行时代码或 `examples/`。

## 验证

- TOML 解析确认项目版本为 `0.1.0`。
- Skill Creator `quick_validate.py` 校验通过。
- `git diff --check` 通过。
- 未运行测试；本次变更仅涉及版本元数据和文档。

## 发布标记

- Git tag：`v0.1.0`（annotated，指向本次发布提交）。
