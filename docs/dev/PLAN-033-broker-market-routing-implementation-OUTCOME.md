# PLAN-033 Broker 多市场路由实施结果

## 结果

已实现 `docs/design/broker-market-routing-20260701-design.md` 中的 Broker 多市场路由设计。

用户现在可以用一个 Broker 同时表达多个市场规则：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001, market=markets.CRYPTO)
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])
```

策略仍然只通过 `self.broker` 下单：

```python
self.broker.order_target_percent("600519.SH", 0.8, price=a_price, portfolio="ashare")
self.broker.order_target_percent("BTCUSDT", 0.8, price=btc_price, portfolio="crypto")
```

## 代码变更

1. `minbt/broker/broker.py`
   - 增加 `_default_market`、`_markets`、`_symbol_market_names`。
   - 增加 `add_market(name, market, symbols)`。
   - 增加 `get_market(symbol)`，返回 market 配置快照。
   - 增加 `_market_for(symbol)` 内部路由。
   - 将订单校验、目标仓位数量标准化、限价单提交、限价单成交、平仓、成交后 T+1 锁仓改为按 symbol 解析 market。
   - 将 `broker.market` 保留为默认 market 的兼容属性别名，避免旧代码直接访问默认市场规则时失效。
   - 在新 dt 到来时按 market 分组处理 T+1 解锁，避免默认 market 或第一个价格 symbol 影响其他市场持仓。

2. `minbt/broker/market.py`
   - `Market.on_new_dt(broker, dt, symbols=None)` 支持只处理指定 symbols。
   - `symbols=None` 保留旧语义：处理 broker 内全部 position。

3. `tests/test_broker.py`
   - 增加一个 Broker 内 A 股和 crypto 同时生效的测试。
   - 覆盖 A 股 100 股一手、T+1 当天不可卖、crypto 小数数量、crypto T+0 当天可卖。
   - 覆盖目标仓位、限价单按 symbol market 路由。
   - 覆盖 `get_market` 返回快照。
   - 覆盖 `add_market` 的空 symbols、重复 symbol、重复 market name、重复映射、运行期已知 symbol 拒绝。

4. `tests/test_api_contract.py`
   - 固化 `Broker.add_market(name, market, symbols)` 和 `Broker.get_market(symbol)` 公开签名。

5. `examples/10_scenario_cross_market.py`
   - 新增跨市场示例：一个 Broker、两个 portfolio、A 股 + crypto。

6. `tests/test_examples.py`
   - 将 `examples/10_scenario_cross_market.py` 纳入示例冒烟测试。

## 文档变更

1. `README.md`
   - 更新市场规则说明为 `market` 默认规则 + `add_market(...)` symbol 路由。
   - 增加跨市场分仓示例。
   - 增加 09 和 10 示例列表。

2. `docs/design/minbt-20260630-system-design.md`
   - 将 portfolio 与 market 的关系改为：portfolio 管资金和持仓隔离，market 按 symbol 路由交易规则。
   - 增加 `add_market(...)` 和 `get_market(...)` 说明。
   - 从“不进入当前 MVP”移除 per-symbol 市场规则，改为仍不做 per-symbol 手续费、默认杠杆和保证金模型。

3. `docs/design/broker-market-routing-20260701-design.md`
   - 状态从“设计稿”改为“已实施”。
   - 记录本实施计划文档。

4. `skills/minbt-usage/SKILL.md`
   - 更新策略开发 skill 的市场示例为 `add_market(...)`。
   - 增加跨市场分仓示例和新示例索引。

## 验证

已执行：

```bash
python -m pytest -q tests/test_broker.py tests/test_api_contract.py tests/test_examples.py
```

结果：

```text
66 passed in 32.38s
```

已执行：

```bash
python -m pytest -q
```

结果：

```text
129 passed in 33.05s
```

已执行：

```bash
python -m compileall -q minbt tests examples
```

结果：通过。

已执行：

```bash
git diff --check
```

结果：通过。

## 当前边界

本次未实现：

- 每个 market 独立手续费率。
- 每个 market 独立默认杠杆。
- 每个 market 独立保证金模型。
- 真实交易所 venue。
- 多 broker 主路径。

这些边界与当前设计一致。
