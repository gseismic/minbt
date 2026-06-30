# PLAN-017 系统设计文档收敛结果

## 完成内容

1. 新增 `docs/design/minbt-20260630-system-design.md`，作为当前唯一有效系统设计稿。
2. 更新 `docs/design/README.md`，索引当前有效设计并说明旧设计已合并删除。
3. 删除旧设计稿：
   - `docs/design/DESIGN-001-broker-account-market-api.md`
   - `docs/design/DESIGN-002-data-feeds-and-callbacks.md`
   - `docs/design/broker-20260629-interface.md`

## 设计结论

1. 用户回调统一推荐 `on_bars(dt, bars)`。
2. 用户交易统一通过 `self.broker`。
3. 退出条件目标设计绑定用户侧 `Order`，不使用 `Trade` 作为用户概念。
4. 标准止盈止损命名为 `stop_loss_price/take_profit_price`。
5. 函数型退出条件使用 `broker.add_exit(order_id, condition=...)`，不混入标准止盈止损参数。
6. 移动止损使用 `trailing_stop_pct/trailing_stop_amount`。
7. 市场差异通过 `Market(...)` 特征和 `markets.*` 预设表达。
8. 限价单当前未实现，目标设计只保留最小 pending limit order。

## 校验

1. `git diff --check -- docs/design` 通过。
2. 已检查 `docs/design` 中只剩当前设计稿和 README。
