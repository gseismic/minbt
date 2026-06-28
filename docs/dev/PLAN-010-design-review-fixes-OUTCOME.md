# PLAN-010 设计 review 修复结果

## 完成内容

1. 更新 `docs/design/DESIGN-001-broker-account-market-api.md`。
2. 更新 `docs/design/DESIGN-002-data-feeds-and-callbacks.md`。
3. 更新 `docs/design/README.md`。

## 主要修复

1. 明确 `initial_cash` 是初始现金，不是初始总权益。
2. 明确初始持仓默认 `leverage=1.0`，并定义 `margin/leverage` 初始化规则。
3. 明确 `available_size/locked_size` 对多头和空头都表示可平/锁定数量。
4. 明确 `close_position` 默认是全平语义，T+1 下不能全平时返回失败，不静默部分平。
5. 将 `MarketModel` 设计为市场特征组合，包含可交易时间、交易日、T+0/T+1、lot size、tick size、费用、是否允许做空、涨跌停等。
6. 明确 `ChinaAStockMarket` 和 `CryptoMarket` 是特征预设组合。
7. 增加 T+1 持仓批次和交易日判断设计。
8. 明确加密市场 symbol 级最小交易数量、最小名义金额、tick size 是后续扩展点。
9. 固化 `broker.add_exit_rule(...)` 推荐签名。
10. 明确 broker 级退出规则使用当前价格和上一轮策略状态。
11. 修正 ATR 止损示例，避免 `atr=None`。
12. 在设计索引中统一全局实施顺序。

## 未实施内容

本次只更新设计文档，未修改代码：

1. 未实现 `Strategy.on_bars`。
2. 未实现 `Exchange.set_bars`。
3. 未实现 `Broker(initial_positions=...)`。
4. 未实现目标仓位接口。
5. 未实现 `MarketModel`。
6. 未实现函数式止盈止损。
7. 未实现限价单。

## 验证

已执行并通过：

```bash
git diff --check
```
