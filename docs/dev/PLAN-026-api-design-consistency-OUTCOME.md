# PLAN-026 API 与设计一致性修复结果

## 已完成

1. 更新 `docs/design/minbt-20260630-system-design.md`：
   - 补全稳定主路径示例，包含 `Broker`、`Strategy`、`Exchange`、`add_strategy()`、`run()`。
   - 在 Exchange 用户接口中补充 `add_strategy(strategy)`。
   - 在 Strategy 用户接口中补充构造函数、参数语义和结果查询辅助接口。
   - 明确 `remove_strategy()` 是高级管理接口，`reset_market_state()` 是内部/测试辅助接口。
   - 修正 `ExitConfig.active` 默认值为 `False`。
   - 修正 `Market.on_order_filled(...)` 内部接口签名，补充 `old_size=0.0` 及 T+1 语义。
   - 将精确 `reason` 字符串改为人读说明，明确稳定判断应依赖 `status` 等结构化字段。
   - 明确 `Broker.on_new_price()`、`process_pending_orders()`、`check_exit_rules()` 是 Exchange 调用的内部运行时接口。
   - 补充 `get_portfolios()`，并把 `get_market_price()`、`get_all_portfolio_equity()` 标注为不推荐的新示例别名。
2. 收紧包级导出：
   - `minbt.broker.__all__` 不再推荐导出 `Portfolio`、`Position`、`Cash`。
   - 保留直接模块路径导入能力，内部测试和维护代码不受影响。
3. 补充接口契约测试：
   - 固定 `Portfolio`、`Position`、`Cash` 不进入 `minbt.broker.__all__`。

## 验证

已运行：

```bash
rg -n "active: bool = True|on_order_filled\\(broker, symbol, qty, price, dt=None, portfolio=\"main\"\\)|reason=\"target unchanged\"|reason=\"position empty\"|reason=\"portfolio empty\"" docs/design/minbt-20260630-system-design.md
pytest -q tests/test_api_contract.py
python -m compileall -q minbt tests examples
pytest -q
git diff --check
```

结果：

- 关键残留搜索无命中。
- `tests/test_api_contract.py`：11 passed。
- `python -m compileall -q minbt tests examples`：通过。
- 全量测试：124 passed。
- `git diff --check`：通过。

## 未做事项

- 未修改核心交易、限价单、退出条件或 T+1 行为。
- 未把内部运行时钩子提升为推荐用户接口。
- 未删除 `Portfolio`、`Position`、`Cash` 模块和直接模块导入能力。
- 未把 `get_market_price()`、`get_all_portfolio_equity()` 等重复别名作为新示例推荐接口。
