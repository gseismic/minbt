# minbt 设计文档索引

## 当前有效设计

- `minbt-20260630-system-design.md`：账户、Strategy、Order、Portfolio、Position、Market、退出条件和限价单边界；其中 Exchange 数据回放部分以本索引下的新稿为准。
- `broker-market-routing-20260701-design.md`：Strategy-Broker 关系和 broker 内多市场路由设计稿，明确保留 `Strategy(..., broker=broker)` 主路径，并通过 `broker.add_market(...)` 支持跨市场规则。
- `data-feed-20260701-design.md`：历史数据接入背景稿；其中旧事件模型和旧回放参数已被新稿替代。
- `exchange-20260921-replay-modes.md`：当前 Exchange 设计与实现契约，定义通用 Bar、News、全量预加载、渐进回放、简单 Feed 门面、通用 CSV/iosql Bar 存储、时间排序、TimeBatch、Broker 估值和未来实时模式边界。
- `pnl-20260920-examples.md`：可手算盈亏示例、净盈亏曲线定义和端到端正确性校验设计。

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

1. 用户回调使用 `on_bars/on_books/on_trades/on_bar/on_news`；`on_bar` 专门接收没有专用回调的自定义 Bar，不恢复旧的 `on_data/on_tick`。
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
12. 跨市场能力优先通过单 broker 内的 `symbol -> Market` 路由设计，不把一个策略多个 broker 作为主路径。
13. 数据源接入推荐通过 `exchange.add_feed(feed)` 扩展，历史 Feed 直接产生 `Bar | News`；`set_bars(...)` 继续服务用户已有数据的最短路径。
14. Exchange 使用 `load_mode="auto"/"preload"/"incremental"`；普通用户使用 `mark_price="kind.field"` 选择估值字段，高级路径再使用精确路由或 callable。

## 阅读顺序

1. 先读 `minbt-20260630-system-design.md` 的“总目标”和“接口分层原则”。
2. 再读 `broker-market-routing-20260701-design.md`，确认 Strategy-Broker 和多市场边界。
3. 再读 `data-feed-20260701-design.md`，了解自动下载、缓存复用的背景；数据模型和回放契约以 Exchange 新稿为准。
4. 再读“典型用户场景”，确认接口是否足够简洁。
5. 实施代码前读“当前实现状态”和“推荐迁移顺序”。
