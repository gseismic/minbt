# PLAN-034 Market Routing 用户接口一致性修复结果

## 结果

已修复 Broker 多市场路由实现和用户接口设计之间的 3 个不一致点。

## 修复内容

1. 移除 `broker.market` 公开可变入口
   - 删除 `Broker.market` property。
   - 默认 market 只能通过 `Broker(..., market=...)` 构造参数设置。
   - 查询市场规则统一使用 `broker.get_market(symbol)`，返回快照。

2. 收紧 `add_market(...)` 为真正配置期接口
   - broker 已有任意订单、pending order、最新价或 position 状态时，`add_market(...)` 直接抛错。
   - 避免回测运行中新增 market routing，导致历史状态和未来规则混杂。

3. 禁止显式 market name 与默认 market name 冲突
   - 如果 `name == _default_market.name`，`add_market(...)` 抛错。
   - 避免两个规则不同的 market 在调试输出中显示同名。

## 测试更新

1. `tests/test_api_contract.py`
   - 增加 `broker.market` 不应存在的契约测试。

2. `tests/test_broker.py`
   - 将原本直接修改 `broker.market.allow_short` 的测试改为修改 `get_market(...)` 快照。
   - 增加默认 market name 冲突测试。
   - 增加交易后对新 symbol 调用 `add_market(...)` 也会拒绝的测试。

## 文档更新

1. `README.md`
   - 说明 `add_market(...)` 应在回测和交易前调用。
   - 说明 `get_market(symbol)` 返回快照，修改返回对象不改变 broker 内部规则。

2. `docs/design/broker-market-routing-20260701-design.md`
   - 明确不提供 `broker.market` 可变属性。
   - 明确 broker 有任意运行状态时不能再 `add_market(...)`。
   - 明确显式 market name 不能与默认 market name 冲突。

3. `docs/design/minbt-20260630-system-design.md`
   - 同步 market routing 用户接口边界。

4. `skills/minbt-usage/SKILL.md`
   - 明确策略开发时不要使用或修改 `broker.market`。

## 验证

已执行：

```bash
python -m pytest -q tests/test_broker.py tests/test_api_contract.py tests/test_examples.py
```

结果：

```text
67 passed in 18.16s
```

已执行：

```bash
python -m pytest -q
```

结果：

```text
130 passed in 45.52s
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

仍不支持：

- 运行期修改 market routing。
- 运行期替换默认 market。
- 每个 market 独立手续费、默认杠杆或保证金模型。

这些边界与当前最简回测系统目标一致。
