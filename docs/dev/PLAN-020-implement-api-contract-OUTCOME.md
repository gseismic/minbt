# PLAN-020 实现最简回测接口契约 - 结果

## 结果摘要

已按 `docs/design/minbt-20260630-system-design.md` 的目标契约完成代码重构，重点是删除开发期旧接口，收敛到“Exchange 接入数据，Strategy 在同一时间截面回调中调用 Broker 交易”的最简模型。

## 已完成变更

1. Exchange
   - 删除用户级 `set_data(...)`。
   - 保留并实现 `set_bars/set_books/set_trades/set_news`。
   - 回调统一为 `on_bars/on_books/on_trades/on_news(dt, data)`。
   - 同一 `dt` 先聚合数据源并更新所有价格，再处理限价挂单和退出条件，最后触发策略回调。
   - 多数据源回调顺序固定为 `on_bars -> on_books -> on_trades -> on_news`。

2. Strategy
   - 删除 `on_data/on_bar` 用户回调。
   - Broker 协议删除 `portfolio_id`。
   - 保留 `market_buy/market_sell/market_order` 少量真实交易快捷方法。

3. Broker
   - 构造函数删除 `portfolio_cash/portfolio_id/initial_positions`。
   - 新增 `Order` 结构，所有订单类接口返回 `Order`。
   - 实现市价单、限价单、撤单、目标仓位、目标金额、目标权重、平仓、关闭组合。
   - 业务失败返回 `Order(status="rejected", reason=...)`。
   - 目标无变化返回 `Order(status="skipped", reason=...)`。
   - 参数错误仍抛出 `ValueError`。
   - 止盈止损改为订单级 `set_exit(order_id, ...)`。
   - 支持固定止损价、固定止盈价、追踪止损百分比、追踪止损金额、自定义函数退出条件。
   - 保留 `add_portfolio(name, cash)`，删除 `add_sub_portfolio` 用户入口。

4. 市场模型
   - 用户接口只导出 `Market` 和 `markets.DEFAULT/CRYPTO/A_STOCK`。
   - 删除 `SimpleMarket/CryptoMarket/ChinaAStockMarket` 用户导出。
   - 市场特征继续支持 T+0/T+1、交易时间、整手、tick、不可做空等规则。

5. 示例
   - 示例脚本统一编号：
     - `examples/01_demo_mini.py`
     - `examples/02_single_symbol_sma.py`
     - `examples/03_multi_symbol_rotation.py`
     - `examples/04_scenario_exit_rules.py`
     - `examples/05_scenario_limit_order.py`
     - `examples/06_scenario_single_breakout.py`
     - `examples/07_scenario_multi_rotation.py`
     - `examples/08_scenario_pairs_mean_reversion.py`
   - `examples/example_utils.py` 适配 `Order.status`。
   - 新增限价单真实场景示例。

6. 文档
   - 更新 `README.md`，改为当前编号示例和新接口说明。
   - README 删除旧兼容接口描述，改为订单级退出条件、限价单和多数据源回调说明。

## 测试结果

已执行：

```bash
python -m compileall minbt examples tests
pytest -q
```

结果：

```text
97 passed
```

## 仍保留的限制

- 限价单和退出条件按当前最新价触发，不模拟 bar 内 high/low 路径。
- 不模拟滑点、部分成交或真实订单簿撮合。
- 当前资金模型仍是保证金账户模型，不是现货账户模型。
- Exchange 不负责拉取或缓存历史数据，用户需要自行准备数据。
