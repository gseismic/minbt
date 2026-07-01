# PLAN-034 Market Routing 用户接口一致性修复

## 背景

对 Broker 多市场路由实现做用户接口一致性 review 后，发现 3 个真实问题：

1. `broker.market` 暴露为可变 live 对象，用户可以绕过 `get_market()` 快照语义直接修改默认市场规则。
2. `add_market(...)` 文档定义为配置期接口，但代码只禁止已知 symbol，允许交易后给新 symbol 增加 market routing。
3. 显式 market name 可以和默认 market name 重名，导致不同规则的 market 显示同名，调试时容易误导。

## 目标

修复代码，使用户接口和设计保持一致：

- 默认 market 只能通过构造参数传入。
- 用户查询 market 只能使用 `get_market(symbol)`，返回快照。
- `add_market(...)` 只能在 broker 没有任何运行状态时调用。
- 显式 market name 不能与默认 market name 重名。

## 实施步骤

1. 移除 `Broker.market` 公开属性。
2. 在 `add_market(...)` 中增加全局配置期检查：
   - 已有订单则拒绝。
   - 已有 pending order 则拒绝。
   - 已有 last price 状态则拒绝。
   - 任一 portfolio 已有 position 状态则拒绝。
3. 在 `add_market(...)` 中拒绝 `name == _default_market.name`。
4. 更新测试：
   - 不再使用 `broker.market` 修改 preset。
   - 增加 `broker.market` 不应存在的契约测试。
   - 增加交易后给新 symbol `add_market(...)` 会拒绝的测试。
   - 增加默认 market name 冲突测试。
5. 更新设计文档、README 和 skill 中关于 market 查询/修改边界的说明。
6. 运行相关测试、全量测试、编译检查和 diff 检查。

## 非目标

- 不增加运行期修改 market routing 的能力。
- 不增加按 market 的手续费、杠杆或保证金模型。
- 不改 `Broker(..., market=...)` 构造参数。
