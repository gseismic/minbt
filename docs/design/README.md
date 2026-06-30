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

1. 用户回调一次性定义为 `on_bars/on_books/on_trades/on_news`，目标设计不保留 `on_data/on_bar`。
2. Exchange 用户入口一次性定义为 `set_bars/set_books/set_trades/set_news`，目标设计不保留 `set_data`。
3. 用户交易统一通过 `self.broker`。
4. 所有下单类接口统一返回 `Order`，无交易用 `status="skipped"`，业务失败用 `status="rejected"`。
5. 市场差异通过 `Market(...)` 特征和 `markets.*` 预设表达，不推荐市场子类。
6. 分仓入口是 `broker.add_portfolio(name, cash)`，用户参数是 `portfolio="..."`。
7. 退出条件应绑定 `Order`，目标接口使用 `order.id`。
8. 标准止盈止损命名为 `stop_loss_price/take_profit_price`，移动止损命名为 `trailing_stop_pct/trailing_stop_amount`。
9. 函数型退出条件使用独立高级接口，不混进标准止盈止损参数。
10. 限价单、撤单和最小 pending limit order 已实现；不模拟队列位置、部分成交和 intrabar 路径。
11. 当前实现仍以 `set_bars/on_bars` 为主路径，同时已定义并实现 `set_books/set_trades/set_news` 的同一时间截面契约。

## 阅读顺序

1. 先读 `minbt-20260630-system-design.md` 的“总目标”和“接口分层原则”。
2. 再读“典型用户场景”，确认接口是否足够简洁。
3. 实施代码前读“当前实现状态”和“推荐迁移顺序”。
