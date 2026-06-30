# PLAN-027 README 与策略开发 Skill 更新结果

## 已完成

1. 重写 `README.md`：
   - 将文档定位改为用户策略开发入口。
   - 补充完整最小回测主路径：`Broker`、`Strategy`、`Exchange.set_bars()`、`add_strategy()`、`run()`。
   - 增加策略开发流程、单标的和多标的策略模板。
   - 明确 bars 数据契约、回调顺序、Broker 交易接口、Order 状态、限价单、退出条件、分仓、市场规则和结果查询。
   - 移除 logger 作为 README 主章节，避免非核心功能干扰最简使用路径。
   - 明确当前设计边界：不模拟滑点、订单簿队列、部分成交和 intrabar 路径。
2. 重写 `skills/minbt-usage/SKILL.md`：
   - 将 skill 从内部维护导向改为用户策略开发导向。
   - 明确 Agent 帮用户写策略时的数据检查、策略模板、Broker 接口选择、退出条件、分仓和市场规则。
   - 明确不推荐在用户策略中使用 `Portfolio`、`Cash`、`Broker.on_new_price()` 等内部接口。
   - 保留最小验证命令。
3. 更新 `skills/minbt-usage/agents/openai.yaml`：
   - 将描述改为面向用户策略开发。
4. 同步修正 `docs/design/README.md`：
   - 修正“限价单当前未实现”的过期描述。
   - 明确 `set_books/set_trades/set_news` 已实现同一时间截面契约。

## 验证

已运行：

```bash
python - <<'PY'
# README 最小示例
PY
pytest -q tests/test_examples.py
pytest -q
python -m compileall -q minbt tests examples
git diff --check
```

结果：

- README 最小示例可运行，最终持仓为 0。
- `tests/test_examples.py`：8 passed。
- 全量测试：124 passed。
- 编译检查：通过。
- `git diff --check`：通过。

## 说明

- 搜索旧接口时，`on_data/on_bar/on_tick/set_data` 只出现在“不保留/不恢复”的说明中，不是推荐用法。
- 本次未修改 minbt 运行时代码。
