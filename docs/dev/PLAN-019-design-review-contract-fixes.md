# PLAN-019 设计 Review 契约修复

## 背景

在密集开发阶段不考虑兼容旧接口，避免接口扩散。当前设计稿仍存在以下问题：

1. 目标设计中仍出现兼容旧接口的叙述。
2. 多数据源同一 `dt` 下会产生多次价格更新、退出检查和策略回调，语义偏复杂。
3. 限价单使用 bar `high/low` 触发，与“不模拟同一根 bar 路径”的原则冲突。
4. `close_portfolio` 引入 `PortfolioCloseResult`，增加用户概念。
5. `clear_exit` 返回 `ExitConfig | None`，与返回值稳定原则冲突。
6. `Order.order_type` 混入 `target`，订单类型和来源语义不清。

## 目标

1. 删除目标设计中的兼容接口示例和兼容叙述。
2. 收紧同一 `dt` 下的数据调度和退出检查语义。
3. 限价单最小规则改为基于当前最新价，不使用 high/low 推断路径。
4. `close_portfolio` 复用 `list[Order]`，不新增结果类型。
5. `clear_exit` 返回稳定的 `ExitConfig`。
6. 将 `Order.order_type` 和 `Order.source` 分离。

## 范围

本计划只修改文档，不修改代码。

## 预期产物

1. 更新 `docs/design/minbt-20260630-system-design.md`。
2. 更新 `docs/design/README.md`。
