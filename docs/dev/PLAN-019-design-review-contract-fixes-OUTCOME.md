# PLAN-019 设计 Review 契约修复结果

## 完成内容

1. 更新 `docs/design/minbt-20260630-system-design.md`。
2. 更新 `docs/design/README.md`。

## 修复结论

1. 删除目标设计中的 `add_sub_portfolio`、`portfolio_id` 下单示例和旧市场工厂推荐/兼容叙述。
2. 明确目标用户接口不暴露 `portfolio_id`、`portfolio_cash`、`initial_positions`。
3. 同一 `dt` 下先更新所有可见价格，再只检查一次 pending order 和退出条件。
4. 限价单触发改为基于当前最新价；bars 数据默认使用 close，不用 high/low 推断同一根 bar 路径。
5. `close_portfolio` 返回 `list[Order]`，不引入 `PortfolioCloseResult`。
6. `clear_exit` 返回 `ExitConfig(active=False)` 表示已无退出条件。
7. `Order.order_type` 只表示 market/limit，用户接口来源用 `Order.source` 表示。
8. README 补充：首批实现仍以 `set_bars/on_bars` 为主路径，books/trades/news 是已定义的目标契约，不强迫首批同时实现。

## 校验

提交前应执行：

1. `git diff --check -- docs/design docs/dev/PLAN-019-design-review-contract-fixes.md docs/dev/PLAN-019-design-review-contract-fixes-OUTCOME.md`
2. 检查目标设计中不再把 `PortfolioCloseResult` 作为返回结构，不再展示 `add_sub_portfolio`，不再把 high/low 作为限价触发规则。
