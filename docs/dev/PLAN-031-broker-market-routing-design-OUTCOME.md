# PLAN-031 broker market routing 设计稿结果

## 完成内容

- 新增 `docs/design/broker-market-routing-20260701-design.md`。
- 更新 `docs/design/README.md` 当前有效设计索引。

## 设计结论

1. 保留 `Strategy(..., broker=broker)` 作为主路径。
2. 策略运行时继续通过 `self.broker` 交易。
3. 一个策略多个 broker 不进入当前主路径。
4. 跨市场能力通过一个 broker 内的 `symbol -> Market` 路由解决。
5. 推荐新增 `broker.add_market(name, market, symbols)`。
6. `Exchange` 继续定位为回测时钟和数据调度器，不表达真实交易所。

## 未改内容

- 未修改代码。
- 未修改 README。
- 未修改主系统设计稿 `minbt-20260630-system-design.md`。

## 后续建议

下一步可以按设计稿的“后续实现顺序”实施 `Broker` 的 market routing。
