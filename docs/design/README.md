# minbt 设计文档索引

## 当前有效设计

- `minbt-20260630-system-design.md`：当前唯一有效系统设计稿，覆盖 Exchange、Strategy、Broker、Order、Portfolio、Position、Market、退出条件、限价单边界和迁移顺序。

## 已合并删除的旧设计

- `DESIGN-001-broker-account-market-api.md`：已合并进当前系统设计。
- `DESIGN-002-data-feeds-and-callbacks.md`：已合并进当前系统设计。
- `broker-20260629-interface.md`：已合并进当前系统设计，并修正 `Trade` 为用户侧 `Order`。

## 当前总原则

minbt 的目标是最简、方便、快捷的回测系统，不做大而全交易所模拟。

稳定用户模型：

```python
class MyStrategy(Strategy):
    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["close"]
        self.broker.order_target_percent("BTCUSDT", 0.8, price=price)
```

核心边界：

- Exchange 负责按时间提供同类数据切片。
- Strategy 负责产生交易意图。
- Broker 是唯一交易入口。
- Order 是用户修改订单关联退出条件的句柄。
- Portfolio 和 Position 负责账户状态。
- Market 负责市场规则差异。

## 当前文档结论

1. 用户回调统一推荐 `on_bars(dt, bars)`。
2. 用户交易统一通过 `self.broker`。
3. 市场差异通过 `Market(...)` 特征和 `markets.*` 预设表达，不推荐市场子类。
4. 分仓入口是 `broker.add_portfolio(name, cash)`，用户参数是 `portfolio="..."`。
5. 退出条件应绑定 `Order`，目标接口使用 `order.id`。
6. 标准止盈止损命名为 `stop_loss_price/take_profit_price`。
7. 函数型退出条件使用独立高级接口，不混进标准止盈止损参数。
8. 限价单当前未实现，未来只做最小 pending limit order。

## 阅读顺序

1. 先读 `minbt-20260630-system-design.md` 的“总目标”和“接口分层原则”。
2. 再读“典型用户场景”，确认接口是否足够简洁。
3. 实施代码前读“当前实现状态”和“推荐迁移顺序”。
