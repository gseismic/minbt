# PLAN-011 移除 initial_positions 主路径设计结果

## 完成内容

1. 更新 `docs/design/DESIGN-001-broker-account-market-api.md`。
2. 更新 `docs/design/README.md`。
3. 保持 `DESIGN-002-data-feeds-and-callbacks.md` 不变。

## 主要变更

1. 明确当前 MVP 只支持从 `initial_cash` 现金开始。
2. 删除 `Broker(initial_positions=...)` 的推荐用户接口。
3. 删除初始持仓字段、初始保证金、初始杠杆等主路径设计。
4. 将 `initial_positions` 和账户快照初始化列为当前明确不进入 MVP。
5. 保留 `available_size/locked_size` 作为 broker 内部状态，用于 T+1 等市场规则。
6. 将典型场景改为从现金开始的加密趋势策略和 A 股 T+1 当日买入后不能同日清仓。
7. 更新全局实施顺序，将 Phase-2 改为“目标仓位与持仓可用性”。

## 未实施内容

本次只更新设计文档，未修改代码。

## 验证

已执行并通过：

```bash
git diff --check
```
