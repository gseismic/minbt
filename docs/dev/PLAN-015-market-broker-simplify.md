# PLAN-015 market-broker-simplify

## 背景

当前 `Broker` 和市场规则接口已经具备最小回测能力，但用户接口仍暴露了一些内部实现痕迹：

1. 市场规则通过 `ChinaAStockMarket`、`CryptoMarket` 这类类名暴露，容易把“市场”理解成要继承扩展的对象，而不是一组市场特征。
2. `Broker.__init__` 暴露 `portfolio_cash`、`portfolio_id`，让用户在创建 broker 时同时理解“总现金、主组合现金、未分配现金”三层概念，不符合最简回测目标。
3. 分仓主接口叫 `add_sub_portfolio`，表达的是内部层级关系；用户真实意图是“增加一个 portfolio”。
4. 交易接口使用 `portfolio_id`，更像内部标识字段；用户接口更适合使用 `portfolio`。

## 目标

本次只做最小必要重构，不引入大而全账户系统：

1. 增加通用 `Market` 配置对象，用 `name` 和一组市场特征表达市场规则。
2. 增加 `markets` 预设模块，提供 `markets.DEFAULT`、`markets.CRYPTO`、`markets.A_STOCK`。
3. 保留旧的 `MarketModel`、`SimpleMarket`、`CryptoMarket`、`ChinaAStockMarket` 兼容入口，但不作为推荐用户接口。
4. `Broker` 默认创建 `main` portfolio，`initial_cash` 表示 broker 初始现金且默认全部进入 `main`。
5. 增加 `broker.add_portfolio(name, cash)`，从 `main` 划拨资金创建新组合。
6. 交易、查询、止盈止损接口支持 `portfolio="xxx"` 作为推荐参数，保留 `portfolio_id` 作为兼容参数。
7. 更新测试、README 和设计索引，保证代码、文档、例子一致。

## 非目标

1. 不实现完整订单簿、限价单撮合或异步订单生命周期。
2. 不实现每个 symbol 独立市场规则。
3. 不实现复杂账户资金调拨 API。
4. 不引入 broker 子类或市场子类作为推荐扩展方式。

## 实施步骤

1. 重写 `minbt/broker/market.py` 的用户主模型为 `Market`。
2. 新增 `minbt/broker/markets.py` 市场预设。
3. 更新 `Broker` 初始化、分仓、下单、查询、退出规则接口。
4. 更新 `Strategy` 的 broker 协议和便利方法。
5. 更新测试用例，从用户主路径验证 `markets.A_STOCK`、`add_portfolio`、`portfolio` 参数。
6. 更新 README 和设计文档索引，标记旧类名为兼容入口。
7. 运行全量测试并做一次代码 review。

## 验收标准

1. `Broker(initial_cash=100000, fee_rate=0.001)` 默认创建 `main` portfolio。
2. `broker.add_portfolio("trend", cash=30000)` 从 `main` 转出资金。
3. `broker.submit_market_order(..., portfolio="trend")` 能在指定组合交易。
4. `Broker(..., market=markets.A_STOCK)` 保持 A 股 T+1、整手、交易时间和不可做空规则。
5. 旧的 `portfolio_id`、`add_sub_portfolio` 和旧市场入口仍能兼容基本调用。
6. 全量测试通过。
