# PLAN-033 Broker 多市场路由实施

## 背景

`docs/design/broker-market-routing-20260701-design.md` 已确定当前阶段的跨市场方案：

- 保留 `Strategy(strategy_id=..., broker=broker)` 主路径。
- 一个策略使用一个 Broker。
- 一个 Broker 支持多个 Portfolio 和多个 Market。
- 通过 `symbol -> Market` 路由交易规则。
- 不引入多 broker 主路径、venue、market 子类或每次下单传 market。

当前代码仍是单一 `self.market` 模型，所有 symbol 使用同一市场规则，无法在一个 Broker 内同时正确处理 A 股 T+1/100 股一手和 crypto T+0/小数数量。

## 目标

实现设计稿中的 Broker 多市场路由能力，使用户可以：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001, market=markets.CRYPTO)
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])
```

之后：

- `600519.SH` 使用 A 股规则。
- 未映射的 `BTCUSDT` 使用默认 crypto 规则。
- 下单、目标仓位、限价单、退出条件触发、平仓、T+1 解锁都按 symbol 路由 market。

## 实施步骤

1. 在 `Broker` 增加 `_default_market`、`_markets`、`_symbol_market_names`，保留 `broker.market` 作为默认 market 的兼容别名。
2. 增加 `Broker.add_market(name, market, symbols)` 和 `Broker.get_market(symbol)`。
3. 在 `add_market` 中校验：
   - name 非空且唯一。
   - symbols 非空。
   - symbol 不重复映射。
   - symbol 不能已经出现在持仓、订单、pending order 或 last price 状态中。
4. 将订单校验、数量标准化、限价单提交、限价单成交、平仓、成交后 T+1 锁仓改为 `_market_for(symbol)`。
5. 修改 `Market.on_new_dt` 支持 `symbols` 参数，并让 Broker 在新 dt 时按 market 分组解锁。
6. 补充测试覆盖：
   - 一个 Broker 内 A 股和 crypto 使用不同规则。
   - A 股必须 100 股一手，crypto 允许小数。
   - A 股 T+1 当天不能卖，crypto T+0 当天可卖。
   - `add_market` 的重复、运行期、已知 symbol 校验。
   - `get_market` 返回快照，修改返回对象不影响内部规则。
   - 默认 `broker.market` 兼容现有测试。
7. 增加跨市场示例，并更新 README 与主设计文档中旧的“两个 broker”跨市场描述。
8. 运行测试，代码自审，生成 OUTCOME 文档并提交。

## 非目标

- 不实现每个 market 独立手续费率。
- 不实现每个 market 独立杠杆或保证金模型。
- 不引入 BrokerGroup。
- 不引入真实交易所 venue 模型。
- 不移除 `broker.market` 兼容别名。
