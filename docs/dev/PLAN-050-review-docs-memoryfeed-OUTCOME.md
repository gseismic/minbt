# PLAN-050 评审反馈修复结果

## 状态

已完成。

## 变更

- 修正 README 中 `binance.BinanceKlineFeed` 示例的缩进，示例可直接复制运行。
- 在 README、当前设计稿和使用技能中补充 `on_bar(dt, bar)` 语义：按单个事件逐条调用，
  同一时间点的多个自定义 Bar 不聚合成截面。
- 明确 `mark_price="kind.field"` 是推荐形式。
- 说明 `(kind, field)`、`(feed_name, kind, field)` 和 callable 是高级用法；特别说明三元组会
  耦合 Feed 名称，Feed 重命名时需要同步修改。
- 说明 `mark_price=None` 表示关闭自动估值。
- 删除 `MemoryFeed.__init__` 中与类属性重复的 `supports_incremental` 和 `ordered` 实例赋值。

## 验证

- 定向测试：`69 passed`。
- 全量测试：`202 passed`。
- `ruff check minbt`：通过。
- `python -m compileall -q minbt tests examples`：通过。
- `git diff --check`：通过。

本次没有改变 Exchange、Broker 或 Strategy 的运行时语义。
