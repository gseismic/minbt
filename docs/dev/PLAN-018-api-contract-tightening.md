# PLAN-018 API 契约收紧

## 背景

系统设计稿已经合并为 `docs/design/minbt-20260630-system-design.md`，但仍存在几个目标契约不够明确的问题：

1. 仍描述 `on_data/on_bar` 兼容回调。
2. books、trades、news 等数据类型被描述为未来扩展，而不是一次性目标设计。
3. 交易接口返回值仍有 `Order | None`，会增加用户理解负担。
4. 退出条件参数的冲突、校验、更新和清除规则不够完整。

## 目标

1. 删除目标设计中的 `on_data/on_bar` 用户接口。
2. 一次性定义 `set_bars/set_books/set_trades/set_news` 和 `on_bars/on_books/on_trades/on_news`。
3. 所有下单类用户接口统一返回 `Order`。
4. 目标仓位无变化返回 `Order(status="skipped")`。
5. 业务失败返回 `Order(status="rejected", reason=...)`。
6. 完整定义 `stop_loss_price/take_profit_price/trailing_stop_pct/trailing_stop_amount` 的组合、冲突、校验和修改规则。

## 范围

本计划只修改文档，不修改代码。

## 预期产物

1. 更新 `docs/design/minbt-20260630-system-design.md`。
2. 更新 `docs/design/README.md`。
