# PLAN-032 broker market routing 设计修复

## 目标

修复 `docs/design/broker-market-routing-20260701-design.md` 中 review 发现的真实设计问题。

## 确认的问题

1. `add_market(...)` 缺少配置期/运行期边界，后续实现可能允许已有持仓、订单或价格的 symbol 被重新分配市场。
2. 多市场路由边界写得过满，未说明第一阶段只路由 `Market` 交易规则，不路由费率、杠杆和保证金模型。
3. `get_market(symbol)` 的返回语义与示例冲突：文档既写对象身份判断，又写返回拷贝。
4. `add_market(name, market, symbols)` 中 `name` 和 `market.name` 的关系未定义。
5. 内部字段命名在“内部状态”和“后续实现顺序”中不一致。

## 修复方案

- 明确 `add_market(...)` 是配置期接口。
- 明确已出现在 positions、orders、pending orders、last_prices 中的 symbol 不允许再通过 `add_market(...)` 映射。
- 明确 `name` 是 broker 内部路由名，内部复制 market 后将 `market.name` 设为 `name`。
- 明确 `get_market(symbol)` 返回只读用途的快照，不保证对象身份。
- 明确第一阶段 market routing 只处理 `Market` 特征，不处理 fee/leverage/margin 差异。
- 统一内部字段名为 `_default_market/_markets/_symbol_market_names`。

## 验证

- 检查文档 diff。
- 执行 `git diff --check`。
