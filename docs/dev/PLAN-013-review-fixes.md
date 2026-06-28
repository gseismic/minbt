# PLAN-013 修复设计实施后的 review 问题

## 背景

对 `PLAN-012` 的实现做代码 review 后，确认以下问题需要修复：

1. `Broker.close_portfolio()` 直接调用 `Portfolio.close_all_positions()`，绕过 `MarketModel`，会破坏 A 股 T+1 等市场规则。
2. `MarketModel.normalize_order_qty()` 已定义但没有进入订单链路，目标金额和目标权重接口容易产生无法成交的非整手数量。
3. `BrokerProtocol` 新增目标仓位方法后，错误提示仍停留在旧协议，用户缺方法时定位困难。
4. `ChinaAStockMarket` 在 `dt=None` 时默认放行，直接手动调用 broker 时会绕过交易时间校验。

## 目标

1. 让 `close_portfolio()` 通过 broker 层 `close_position()` 平仓，保留市场规则校验。
2. 在订单链路中接入 `MarketModel.normalize_order_qty()`。
3. 为 `ChinaAStockMarket` 实现按整手向 0 方向规范化目标订单数量。
4. 让 A 股市场在没有 `dt` 时拒绝交易，避免静默跳过交易时间校验。
5. 修正 `BrokerProtocol` 错误信息，列出完整必需方法。
6. 增加回归测试覆盖上述问题。

## 非目标

1. 不实现限价单、挂单式止损或追踪止损。
2. 不实现复杂订单状态机。
3. 不实现批量调仓或原子 rebalance。
4. 不实现每个 symbol 独立交易规则。

## 验证

1. 运行新增/相关测试。
2. 运行全量 `pytest -q`。
3. 运行 `python -m compileall -q minbt tests examples`。
4. 运行 `git diff --check`。
