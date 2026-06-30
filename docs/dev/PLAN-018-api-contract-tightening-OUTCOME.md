# PLAN-018 API 契约收紧结果

## 完成内容

1. 更新 `docs/design/minbt-20260630-system-design.md`。
2. 更新 `docs/design/README.md`。

## 设计结论

1. 目标设计不保留 `set_data/on_data/on_bar`。
2. 数据源和回调一次性定义为 bars、books、trades、news 四类。
3. 多数据源同一 `dt` 下按 `on_bars -> on_books -> on_trades -> on_news` 调度。
4. 所有下单类接口统一返回 `Order`，不再使用 `Order | None`。
5. 无交易场景返回 `Order(status="skipped")`。
6. 业务失败返回 `Order(status="rejected", reason=...)`。
7. `trailing_stop_pct` 和 `trailing_stop_amount` 同一次设置冲突。
8. 标准止盈止损、移动止损、函数型退出条件的设置、更新、清除和查询语义已明确。

## 校验

提交前应执行：

1. `git diff --check -- docs/design docs/dev/PLAN-018-api-contract-tightening.md docs/dev/PLAN-018-api-contract-tightening-OUTCOME.md`
2. 检查 `docs/design` 中不应出现 `on_data/on_bar` 作为目标用户接口。
