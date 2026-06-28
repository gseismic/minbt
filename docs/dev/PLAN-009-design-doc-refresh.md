# PLAN-009 设计文档系统更新

## 背景

近期讨论已经形成新的设计结论：

- 当前回调方向是 `on_bars(dt, bars)`，不是 `on_tick(dt, rows)`。
- 盘口类未来回调应使用 `on_books(dt, books)`，不是 `on_orderbooks(dt, orderbooks)`。
- Broker 应支持真实账户初始状态，不应只支持现金启动。
- 订单动作使用 `qty`，账户状态使用 `size`。
- 初始持仓需要 `available_size/locked_size` 表达 T+1、冻结和可平数量。
- 多市场不应通过 Broker 子类或字符串分支实现，推荐 `Broker + MarketModel`。
- 止盈止损应以函数式退出规则为核心，常规百分比止盈止损只是 helper。

现有 `docs/design` 中仍有旧命名和过期方案，需要系统整理。

## 目标

1. 重写 Broker 相关设计稿，覆盖账户初始状态、多市场、目标仓位、函数式止盈止损和限价单边界。
2. 更新数据回调设计稿，统一 `on_bars/on_books/on_trades/on_news`。
3. 删除或标记过期设计，避免 `on_tick/on_orderbooks` 继续作为推荐方向。
4. 新增设计文档索引，明确当前有效文档和未实现能力。

## 不做

1. 不修改核心代码。
2. 不修改 README。
3. 不迁移 examples。
4. 不实现新接口。

## 验证

1. 检查设计文档中不再把 `on_tick` 作为推荐接口。
2. 检查盘口未来命名使用 `on_books`。
3. 检查 broker 设计明确区分 `qty` 和 `size`。
4. 运行 `git diff --check`。

