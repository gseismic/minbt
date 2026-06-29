# PLAN-014 修复目标规范化与 A 股 dt 边界结果

## 结果

已修复再次 review 确认的问题。

## 已修复

1. `submit_market_order()` 默认不再做数量规范化，用户显式数量必须满足市场规则。
2. `order_target_size/value/percent()` 路径继续启用市场数量规范化。
3. `ChinaAStockMarket` 拒绝数字型 `dt`，避免 Exchange 无 `date_key` 时把行号误当成交易日期。
4. `BrokerProtocol.submit_market_order()` 类型签名同步新增 `normalize_qty` 参数。

## 测试覆盖

新增测试覆盖：

1. A 股显式市价单 `qty=150` 时拒单，不静默成交 100。
2. A 股目标金额下单仍按整手规范化。
3. A 股数据不传 `date_key` 时，Exchange 行号 `dt` 不能通过交易时间校验。

## 验证

已运行：

```bash
pytest -q tests/test_design_mvp.py
pytest -q
python -m compileall -q minbt tests examples
git diff --check
```

结果：

- `tests/test_design_mvp.py`：10 passed。
- 全量测试：83 passed。
- 编译检查通过。
- `git diff --check` 通过。
