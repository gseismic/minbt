# PLAN-002-kernel-review-OUTCOME

## 审查结果
- `Position.commit_open_new` 直接收到 `qty=0` 时会进入未定义变量路径，属于仓位内核边界缺陷。
- `Portfolio.on_new_price` 会为无持仓标的创建空 `Position`，行情广播会污染组合仓位表。
- `Broker.add_sub_portfolio` 允许重复 `portfolio_id`，会覆盖原组合并重复扣减 `remaining_free_cash`。
- `Broker.submit_market_order` 在校验目标组合前会更新 broker 行情状态，错误订单可能污染状态。
- `Broker.submit_market_order` 在未传价格且无最新价时会继续进入下单流程，错误信息不明确且可能创建空仓位。
- `Exchange.run` 在空行情数据上会执行 `total_time / step`，触发除零错误。

## 修复内容
- `Position.commit_open_new` 明确拒绝零数量开仓。
- `Portfolio._update_pnl_get_margin_level` 在无持仓时不创建空仓位。
- `Broker.add_sub_portfolio` 增加重复组合 ID 校验。
- `Broker.submit_market_order` 先校验组合存在，并对缺失市价抛出明确 `ValueError`。
- `Broker` 显式传入 `portfolio_cash == initial_cash` 时与默认行为保持一致。
- `Exchange.run` 对零步行情输出 `0 steps`，不再除以 0。

## 测试覆盖
- 新增 `Position` 零数量开仓测试。
- 新增 `Portfolio` 行情更新不创建空仓位测试。
- 新增 `Broker` 重复组合、无效组合下单、缺失市价测试。
- 新增 `Exchange` 空行情回放测试。

## 验证结果
- `pytest -q tests/test_position.py tests/test_portfolio.py`: 16 passed，1 warning。
- `pytest -q tests/test_broker.py tests/test_exchange.py`: 5 passed，1 warning。
- `pytest -q`: 43 passed，1 warning。
- `python -m pytest -q`: 43 passed，1 warning。
- `git diff --check`: 通过。

## 剩余风险
- 测试环境仍保留 polars 的 `Polars binary is missing!` warning，本轮未处理该环境问题。
