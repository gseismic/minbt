# PLAN-009 设计文档系统更新结果

## 完成内容

1. 重写 `docs/design/DESIGN-001-broker-account-market-api.md`。
2. 重写 `docs/design/DESIGN-002-data-feeds-and-callbacks.md`。
3. 新增 `docs/design/README.md` 作为设计文档索引。
4. 删除旧文件 `docs/design/DESIGN-001-user-order-exit-api.md`。

## 主要设计结论

1. Broker 是唯一交易入口，Strategy 不增加交易语法糖。
2. 订单动作使用 `qty`，账户状态使用 `size`。
3. 初始账户支持 `initial_cash + initial_positions`。
4. 初始持仓字段使用 `size/cost_price/available_size/locked_size`。
5. 多市场扩展使用 `Broker + MarketModel`，不使用 Broker 子类或字符串分支。
6. 函数式止盈止损是核心能力，常规止盈止损是 helper。
7. 限价单延后，只保留最小设计边界。
8. 数据回调统一为 `on_xx(dt, data)`。
9. 当前 MVP 是 `on_bars(dt, bars)`。
10. 未来盘口类数据使用 `on_books(dt, books)`，不使用 `on_orderbooks`。

## 未实施内容

本次只更新设计文档，未修改代码：

1. 未实现 `Strategy.on_bars`。
2. 未实现 `Exchange.set_bars`。
3. 未实现 `Broker(initial_positions=...)`。
4. 未实现目标仓位接口。
5. 未实现函数式止盈止损。
6. 未实现 `MarketModel`。
7. 未实现限价单。

## 验证

已执行并通过：

```bash
git diff --check
```
