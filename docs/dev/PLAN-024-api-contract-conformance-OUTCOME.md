# PLAN-024 用户 API 契约收敛 - 结果

## 真实性复核

计划中的接口偏差均确认真实存在，具体包括：

1. 缺少市场价格时返回 rejected，而不是抛异常。
2. terminal 订单撤单会产生新的 skipped 订单。
3. 订单查询缺少筛选。
4. 持仓查询会创建空持仓。
5. portfolio 查询参数位置与设计不同。
6. 订单接口暴露内部 `source/normalize_qty`。
7. Strategy 和包顶层仍有设计外入口。
8. usage skill 仍描述旧接口和失效示例路径。

## 已完成

1. 缺少市场价格时抛 `ValueError`，不创建订单。
2. terminal 订单撤单返回原订单且不新增记录。
3. pending 撤单更新原挂单并返回取消动作 Order。
4. `get_orders()` 支持 portfolio 和 symbol 筛选。
5. `get_position()` 改为无副作用查询。
6. 现金、权益和持仓查询支持设计规定的 positional portfolio。
7. `get_active_order()` 校验 portfolio 是否存在。
8. 内部订单来源和数量规范化参数迁移到私有方法。
9. 交易接口的 leverage、price_dt、portfolio 和退出参数收敛为 keyword-only。
10. `add_exit()` 的关键字参数顺序与设计一致。
11. 删除 Strategy 交易语法糖和公开 `MarketModel`。
12. 新增独立 API 契约测试，覆盖参数名称、顺序、种类、默认值和旧入口。
13. README 修正数据必需字段、缺价异常、查询接口、函数退出调用和限价资金语义。
14. usage skill 删除全部旧兼容流程并更新编号示例和验证命令。
15. 系统设计更新限价单边界和当前实现状态，删除已经完成的迁移待办。
16. review 补充强平后的退出生命周期清理，避免返回过期 active order。

## 原始问题验收矩阵

|问题|修复证据|
|---|---|
|组合关闭非原子|`test_close_portfolio_preflight_prevents_partial_close`|
|限价单成交后退出校验抛异常|`test_limit_order_exit_validation_is_atomic_when_position_direction_changes`|
|T+1 跨零绕过锁定|`test_t1_market_rejects_cross_zero_sale_of_locked_long_position`|
|旧订单控制新持仓|`test_expired_order_cannot_control_reopened_position`|
|限价单提交不检查资金|`test_limit_order_rejects_insufficient_cash_at_submission`|
|terminal 撤单创建新订单|`test_cancel_order_returns_clear_result_for_done_order`|
|缺少市场价格返回 rejected|`test_submit_market_order_raises_when_market_price_is_missing`|
|callable state 不持久化|`test_callable_exit_state_is_initialized_once_and_persists`|
|查询接口缺失或有副作用|`test_order_queries_support_filters_and_do_not_create_positions`|
|公开模型和签名漂移|`tests/test_api_contract.py`、`test_exit_config_is_public_snapshot`|

## 验证

```text
pytest -q tests/test_api_contract.py
10 passed

pytest -q tests/test_broker.py tests/test_api_contract.py
51 passed

pytest -q tests/test_api_contract.py tests/test_examples.py tests/test_design_mvp.py
23 passed

python -m compileall -q minbt tests examples
通过

pytest -q
123 passed

git diff --check
通过
```

## 结论

`PLAN-024` 已完成。当前公开 API、用户文档、usage skill 和系统设计状态已统一到 `docs/design/minbt-20260630-system-design.md` 定义的 MVP 契约。
