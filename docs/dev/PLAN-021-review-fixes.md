# PLAN-021 修复 review 发现的问题

## 背景

系统 review 后确认以下问题真实存在：

- `Strategy` 仍从 `pyta_dev.utils.vector` 懒加载，未按要求切到 `pyta2.utils.vector`。
- T+1 且允许做空的市场中，空头反手成多头时会按买入总量锁仓，而不是按新增多头净额锁仓，可能成交后抛异常。
- `cancel_order()` 对已成交或已拒绝订单直接返回原订单，用户无法判断撤单动作没有生效。
- `submit_limit_order()` 暴露无效的 `source` 参数，默认值还是错误的 `target_value`，污染用户接口。

## 目标

- 将 pyta 导入、可选依赖、README 和测试从 `pyta_dev` 切换到 `pyta2`。
- 修复 T+1 双向反手时的锁仓数量，只锁定新增多头净额。
- 让 `cancel_order()` 对非 pending 订单返回清晰的 `cancel_order` 动作结果。
- 删除 `submit_limit_order()` 的用户级 `source` 参数。
- 补充覆盖上述行为的测试。

## 验收

- `rg "pyta_dev" minbt tests README.md setup.py` 无结果。
- `pytest tests/test_strategy.py -q` 通过。
- `pytest tests/test_broker.py -q` 通过。
- `pytest -q` 通过。
