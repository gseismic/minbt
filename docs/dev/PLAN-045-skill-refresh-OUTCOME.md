# PLAN-045：同步 minbt 使用技能契约——实施结果

## 状态

已完成。`./skills/minbt-usage` 已按当前源码、README、示例和公开测试契约完成审查与更新。

## 变更摘要

### `skills/minbt-usage/SKILL.md`

- 将 frontmatter 描述改为带具体触发短语的第三人称描述，并明确技能面向用户策略/回测，不负责
  minbt 内部实现。
- 补充 `set_books`、`set_trades`、`set_news` 及对应回调，明确同一 `dt` 的价格更新、broker 处理和
  `bars → books → trades → news` 回调顺序。
- 补充 `run(streaming=None/True/False)` 的自动选择边界，说明 Binance Feed 的物化路径以及 CSV/iosql
  Feed 的流式适用场景。
- 同步 CSV/iosql 的 `[start, end)` 区间、fail-fast 数据校验、iosql 版本与 `batch_size` 语义，并记录
  流式与物化路径的参考内存取舍。
- 补充订单状态集合、限价单触发/资金/撮合边界和 `close_portfolio()` 的 pending 订单语义。
- 补充净盈亏曲线定义、默认杠杆单次开平仓的独立手算公式和专项验证命令。
- 保留并整合工作区中已有的 PnL 示例入口与历史查询契约更新。

### `skills/minbt-usage/agents/openai.yaml`

- 将 UI 描述从单纯“写策略”扩展为“构建并验证策略”。
- 将默认提示扩展为支持本地 bars 或数据 Feed 的策略编写与验证。

## 验证结果

```text
quick_validate.py skills/minbt-usage: Skill is valid!
YAML 元数据检查: valid
python -m pytest -q: 213 passed in 16.78s
python -m compileall -q minbt tests examples: passed
git diff --check: passed
python examples/00_pnl_sanity_check.py: passed，三组理论盈亏均匹配
技能引用的 examples 路径检查: passed
```

## 范围说明

本次未修改 minbt 运行时代码，也未覆盖工作区中原有的 README、测试、PnL 示例、Review 报告和
`HANDOFF.md` 等未提交变更；新增的本计划和结果文件仅记录本次技能更新。
