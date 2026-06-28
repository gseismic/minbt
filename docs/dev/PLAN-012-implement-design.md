# PLAN-012 实施当前 MVP 设计

## 背景

当前有效设计已经收敛：

- minbt 目标是最简、方便、快捷的回测系统。
- 当前 MVP 从现金开始，不支持 `Broker(initial_positions=...)`。
- 策略主回调应统一为 `on_bars(dt, bars)`。
- 交易入口保持在 `broker`。
- Broker 应支持目标仓位接口。
- MarketModel 负责市场规则差异。
- 函数式止盈止损是推荐退出规则能力。

实施前代码仍停留在旧接口：

- `Exchange.set_data(...)`。
- `Strategy.on_data(row)`。
- `Strategy.on_bar(dt, rows_by_symbol)`。
- Broker 只有市价单，限价单和止盈止损未实现。

## 目标

1. 实现 `Exchange.set_bars(...)`，兼容 `set_data(...)`。
2. 实现 `Strategy.on_bars(dt, bars)`，并让 `Exchange.run()` 优先调用 `on_bars`。
3. 保留旧 `on_bar/on_data` 兼容路径。
4. 实现 `Broker.order_target_size(...)`。
5. 实现 `Broker.order_target_value(...)`。
6. 实现 `Broker.order_target_percent(...)`。
7. 引入最小 `MarketModel/SimpleMarket/ChinaAStockMarket/CryptoMarket`。
8. 支持 `Position.available_size/locked_size` 内部状态。
9. 让 `close_position` 在可用持仓不足时默认失败，不静默部分平。
10. 实现函数式退出规则和 `stop_loss_pct/take_profit_pct` helper。
11. 在 `Exchange.run()` 中接入 broker 退出规则检查。
12. 增加测试覆盖新接口和关键兼容行为。

## 不做

1. 不实现 `Broker(initial_positions=...)`。
2. 不实现 `on_books/on_trades/on_news`。
3. 不实现限价单。
4. 不实现复杂订单状态机。
5. 不修改已有脏改动文件，除非实施必须。

## 验证

1. 新增测试覆盖 `on_bars/set_bars`。
2. 新增测试覆盖目标仓位接口。
3. 新增测试覆盖 A 股 T+1 当日不可卖。
4. 新增测试覆盖函数式退出规则。
5. 运行相关测试。
6. 尽量运行全量 `pytest`。
