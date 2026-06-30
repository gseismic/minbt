# PLAN-024 用户 API 契约收敛

## 背景

复核确认公开接口仍有以下设计偏差：

1. 找不到市场价格时返回 rejected Order，而设计要求抛出异常。
2. 撤销 terminal 订单会创建新的 skipped Order，而设计要求返回原订单当前状态。
3. `get_orders()` 缺少 portfolio 和 symbol 筛选。
4. `get_position()` 默认创建空持仓并暴露内部 `create_if_missing` 参数。
5. 现金和持仓查询的 portfolio 参数位置与设计不一致。
6. 市价单和目标仓位接口暴露内部 `source/normalize_qty` 参数。
7. Strategy 仍提供交易语法糖，顶层仍导出 `MarketModel`。
8. minbt usage skill 仍描述已删除的旧接口。

## 目标

1. 公开签名、返回值和异常语义与当前有效系统设计一致。
2. 内部控制参数不进入用户接口。
3. 查询接口不产生账户副作用。
4. README、示例、skill 和设计现状描述与代码一致。

## 实施方案

1. 找不到市场价格时抛出 `ValueError`，且不创建 Order。
2. 撤销 filled、rejected、canceled 或 skipped 订单时返回原订单，不新增记录。
3. 成功撤销 pending 订单保留独立 `source="cancel_order"` 结果，同时更新原订单状态。
4. 实现 `get_orders(*, portfolio=None, symbol=None)`。
5. 将公开 `get_position()` 改为无副作用查询；内部创建和查找持仓使用私有方法。
6. 查询接口接受设计规定的 positional portfolio，并将 `None` 解析为 `main`。
7. `get_active_order()` 对不存在的 portfolio 抛出 `ValueError`。
8. 使用私有订单提交方法承载 `source/normalize_qty`，从公开方法删除这些参数。
9. 将 leverage、price_dt、portfolio 调整为设计规定的 keyword-only 参数。
10. 将 `add_exit(condition=...)` 调整为 condition keyword-only。
11. 删除 `Strategy.market_buy/market_sell/market_order`。
12. 删除公开 `MarketModel` 别名。
13. 增加 `inspect.signature()` 契约测试。
14. 更新 README、示例、usage skill 和设计文档中的当前实现说明。

## 测试

1. 缺少市场价格抛异常且订单列表不变。
2. terminal 撤单返回相同对象且订单列表不变。
3. 成功撤单行为和 pending 元数据清理正确。
4. `get_orders()` 单条件和组合筛选正确。
5. 查询未知持仓返回 `None` 且不创建空持仓。
6. 现金、权益和持仓查询的位置参数与关键字参数均符合设计。
7. 公开签名不存在 `source/normalize_qty/create_if_missing`。
8. Strategy 和顶层包不再暴露设计外入口。
9. README 和全部示例可执行。

## 验收

1. 新增系统设计契约测试通过。
2. `pytest -q` 全量通过。
3. `python -m compileall minbt tests examples` 通过。
4. 搜索确认旧接口和旧参数不再出现在用户文档及示例中。
