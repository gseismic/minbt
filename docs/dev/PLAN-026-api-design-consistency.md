# PLAN-026 API 与设计一致性修复

## 目标

修复近期 review 发现的用户接口与设计文档不一致问题，同时保持 minbt 的最简回测目标，不把内部运行时钩子和重复别名扩散为推荐用户接口。

## 范围

1. 更新 `docs/design/minbt-20260630-system-design.md`：
   - 补全稳定主路径示例，展示 `Broker`、`Strategy`、`Exchange.add_strategy()`、`Exchange.run()` 的完整闭环。
   - 补全 `Exchange.add_strategy()` 和 `Strategy.__init__()` 这两个主路径必需接口。
   - 修正 `ExitConfig.active` 默认值，应为 `False`。
   - 修正 `Market.on_order_filled(...)` 内部接口签名，补充 `old_size` 及其语义。
   - 将 `reason` 描述从精确字符串改为人读说明，避免把英文文本固化为稳定契约。
   - 明确 `remove_strategy()`、Strategy 历史查询、Broker 辅助查询、运行时钩子的接口分层。
2. 收紧包级导出：
   - `minbt.broker` 不再通过 `__all__` 推荐暴露 `Portfolio`、`Cash` 这类内部对象。
   - 保留直接模块路径导入能力，避免影响内部测试和维护。
3. 验证：
   - 运行接口契约测试。
   - 运行全量测试。
   - 检查文档和代码中关键不一致项。

## 非目标

- 不改核心撮合、下单和退出条件行为。
- 不删除已有内部模块。
- 不把 `on_new_price()`、`process_pending_orders()`、`check_exit_rules()` 作为推荐用户接口。
- 不把 `get_market_price()`、`get_all_portfolio_equity()` 等重复别名升级为推荐用户接口。
