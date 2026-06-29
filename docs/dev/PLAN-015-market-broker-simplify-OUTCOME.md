# PLAN-015 market-broker-simplify 结果

## 实施结果

完成。

本次围绕“最简回测系统”的目标，收敛了市场规则和 broker 分仓接口：

1. 新增 `Market(...)` 市场特征配置对象。
2. 新增 `minbt.broker.markets` 预设模块，并从 `minbt` 导出 `markets`。
3. 新增推荐市场预设：
   - `markets.DEFAULT`
   - `markets.CRYPTO`
   - `markets.A_STOCK`
4. 保留旧入口作为兼容：
   - `MarketModel = Market`
   - `SimpleMarket()`
   - `CryptoMarket()`
   - `ChinaAStockMarket()`
5. `Broker` 默认 portfolio 从历史 `default` 改为 `main`。
6. `Broker(initial_cash=...)` 默认把全部初始现金放入 `main`。
7. 新增 `broker.add_portfolio(name, cash)`，从 `main` 划拨资金创建新组合。
8. 下单、目标仓位、查询、退出规则接口支持推荐参数 `portfolio="xxx"`。
9. 保留 `portfolio_id` 和 `add_sub_portfolio` 作为兼容入口。
10. `Broker` 初始化时复制传入的 `Market`，避免多个 broker 共享 `markets.A_STOCK` 等预设对象造成状态污染。
11. 更新 README、设计文档索引、`DESIGN-001` 和 `skills/minbt-usage`。

## 用户主路径

市场：

```python
from minbt import Broker, markets

broker = Broker(initial_cash=100_000, fee_rate=0.0003, market=markets.A_STOCK)
```

分仓：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001)
broker.add_portfolio("trend", cash=30_000)

broker.order_target_percent("BTCUSDT", 0.8, price=100, portfolio="trend")
```

自定义市场：

```python
from minbt import Market

market = Market(
    name="AStock",
    allow_short=False,
    t_plus=1,
    lot_size=100,
    tick_size=0.01,
    require_dt=True,
)
```

## 测试覆盖

新增或更新的测试覆盖：

1. 默认 `main` portfolio。
2. `add_portfolio` 从 `main` 划拨资金。
3. `add_portfolio` 拒绝重复名称和超额划拨。
4. `portfolio="alt"` 能指定组合下单和查询。
5. 关闭非 `main` portfolio 后现金回到 `main`。
6. 旧 `portfolio_cash/add_sub_portfolio` 模式仍能兼容统计未分配现金。
7. `markets.A_STOCK` 保持 A 股 T+1、整手、交易时间和不可做空规则。
8. `markets.A_STOCK` 预设在多个 broker 间不会共享可变状态。
9. `Strategy.get_broker_stats(portfolio=...)` 使用推荐参数。

## 系统 Review 结论

未发现需要继续修复的确定性缺陷。

已在 review 中修复的问题：

1. `markets.A_STOCK` 是模块级对象，如果 broker 直接持有同一实例，后续修改 `broker.market` 会污染其他 broker；已改为 `Broker.__init__` 内复制传入 market。

保留的设计取舍：

1. `portfolio_cash`、`portfolio_id`、`add_sub_portfolio` 继续存在，仅为兼容旧代码，不作为推荐接口。
2. `remaining_free_cash` 继续存在，仅服务旧 `portfolio_cash/add_sub_portfolio` 模式。
3. `Market` 当前只支持 T+0/T+1，不做 T+n。
4. `markets.A_STOCK` 仍是最小 A 股规则，不包含涨跌停、真实交易日历、停牌和每个 symbol 独立最小交易单元。
5. `add_portfolio` 是资金划拨，不是完整账户转账系统；当前 MVP 不实现复杂资金流水。

## 验证结果

已通过：

```bash
pytest -q
python -m compileall -q minbt tests examples
git diff --check
```

结果：

- `88 passed`
- compileall 无错误
- diff check 无错误

## 后续建议

1. 下一步优先保持市价回测路径稳定，不急于扩展大而全账户系统。
2. 如果继续推进交易能力，建议做最小限价单，并明确 pending order 的生命周期。
3. 如果继续推进市场规则，建议优先做 per-symbol 最小交易单位，而不是抽象复杂规则引擎。
