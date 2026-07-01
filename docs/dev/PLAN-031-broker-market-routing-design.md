# PLAN-031 broker market routing 设计稿

## 目标

把关于 `Strategy`、`Broker`、多 broker、多市场和 `broker.add_market(...)` 的讨论结果形成设计稿。

## 范围

- 新增 `docs/design/broker-market-routing-20260701-design.md`。
- 更新 `docs/design/README.md` 设计索引。
- 不改代码。

## 设计重点

1. 判断 `Strategy` 是否应该持有 `broker`。
2. 判断一个策略多个 broker 是否进入主路径。
3. 定义一个 broker 内支持多市场的最小接口。
4. 明确当前代码已经具备的能力和真实缺口。
5. 给出后续实现边界，避免把 minbt 做成大而全交易所模拟。

## 验证

- 检查文档内容是否与当前 minbt 最简回测目标一致。
- 检查设计索引是否能指向新文档。
