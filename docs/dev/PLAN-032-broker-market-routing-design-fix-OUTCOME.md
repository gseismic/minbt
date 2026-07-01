# PLAN-032 broker market routing 设计修复结果

## 完成内容

- 修复 `docs/design/broker-market-routing-20260701-design.md` 中 review 发现的设计契约问题。

## 确认结果

本次 review 中的问题均真实存在，但性质是设计契约不完整，不是当前代码实现错误。

已修复：

1. 明确 `add_market(...)` 是配置期接口。
2. 明确已出现在 positions、orders、pending orders、last_prices 中的 symbol 不能再通过 `add_market(...)` 映射。
3. 明确第一阶段 market routing 只路由 `Market` 交易规则，不路由 fee/leverage/margin。
4. 明确 `get_market(symbol)` 返回 Market 配置快照，不保证对象身份，修改返回对象不影响 broker 内部。
5. 明确 `name` 是 broker 路由名，内部复制 market 后将复制对象的 `name` 设置为该路由名。
6. 统一内部字段命名为 `_default_market/_markets/_symbol_market_names`。

## 验证

- 已执行 `git diff --check`。

## 未改内容

- 未修改代码。
- 未修改 README。
