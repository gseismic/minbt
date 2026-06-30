# PLAN-021 修复 review 发现的问题 - 结果

## 真实性判断

本轮 review 中提出的四个问题均真实存在：

1. `pyta2` 切换未完成
   - `Strategy` 仍从 `pyta_dev.utils.vector` 导入。
   - `setup.py` 可选依赖仍是 `pyta_dev`。
   - README 仍说明 `pyta_dev`。

2. T+1 双向反手锁仓错误
   - 在 `Market(t_plus=1, allow_short=True)` 下，空头 `-100` 后买入 `150`，最终多头只有 `50`，但旧逻辑尝试锁定 `150`，会在成交后抛出 `ValueError`。

3. 撤销非 pending 订单反馈不清晰
   - `cancel_order(filled_order.id)` 旧逻辑直接返回原成交订单，用户无法判断撤单动作没有生效。

4. 限价单签名污染
   - `submit_limit_order()` 暴露无效 `source` 参数，默认值还是 `target_value`，但内部硬编码 `submit_limit_order`。

## 修复内容

1. pyta2
   - `Strategy` 改为从 `pyta2.utils.vector` 懒加载 `NumpyVector` 和 `VectorTable`。
   - `setup.py` 的 `pyta` extra 改为安装 `pyta2`。
   - README 改为说明 `pyta2`。
   - 测试中的缺失依赖模拟改为拦截 `pyta2`。

2. T+1 锁仓
   - `Broker` 在订单成交后把成交前仓位 `old_size` 传给 `Market.on_order_filled()`。
   - `Market.on_order_filled()` 只锁定新增多头净额：
     - `opened_size = max(new_long_size - old_long_size, 0)`
   - 反手时不会再按买入总量错误锁仓。

3. 撤单反馈
   - `cancel_order()` 撤销 pending 订单时：
     - 原挂单状态更新为 `canceled`。
     - 返回一个 `source="cancel_order"`、`status="canceled"` 的撤单结果。
   - 对已成交、已拒绝、已取消等非 pending 订单：
     - 返回 `source="cancel_order"`、`status="skipped"`，并提供 `reason`。

4. 限价单签名
   - 删除 `submit_limit_order()` 的用户级 `source` 参数。
   - 保留 `order_target_value()` 的内部 `source` 参数，用于正确表达目标仓位接口来源。

## 新增/更新测试

- 增强 `test_submit_limit_order_can_fill_and_cancel`，验证撤单结果和原挂单状态。
- 新增 `test_cancel_order_returns_clear_result_for_done_order`。
- 新增 `test_submit_limit_order_does_not_expose_source_parameter`。
- 新增 `test_t1_market_locks_only_new_long_size_when_reversing_short_to_long`。
- 更新 `test_strategy_history_without_pyta`，模拟 `pyta2` 缺失。

## 验证结果

已执行：

```bash
python -m compileall minbt tests
pytest tests/test_strategy.py tests/test_broker.py -q
rg "pyta_dev" minbt tests README.md setup.py
pytest -q
```

结果：

```text
33 passed
100 passed
```

`rg "pyta_dev" minbt tests README.md setup.py` 无输出，说明用户面代码、测试、README 和安装依赖已切换到 `pyta2`。
