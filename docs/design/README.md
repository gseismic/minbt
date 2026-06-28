# minbt 设计文档索引

## 当前有效设计

- `DESIGN-001-broker-account-market-api.md`：Broker 用户接口、账户初始状态、多市场扩展、函数式止盈止损、限价单边界。
- `DESIGN-002-data-feeds-and-callbacks.md`：Exchange 数据接入、`on_bars` 当前回调、未来 `on_books/on_trades/on_news` 扩展。

## 已替代设计

- `DESIGN-001-user-order-exit-api.md` 已被删除并重写为 `DESIGN-001-broker-account-market-api.md`。
- 旧设计中的 `on_tick(dt, rows)` 不再作为推荐方向。
- 旧设计中的 `on_orderbooks(dt, orderbooks)` 改为 `on_books(dt, books)`。

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
- Portfolio 和 Position 负责账户状态。
- MarketModel 负责市场规则差异。

## 全局推荐实施顺序

### Phase-1：统一 bars 用户回调

1. `Strategy.on_bars(dt, bars)`。
2. `Exchange.set_bars(...)`。
3. `Exchange.set_data(...)` 兼容为 bars 入口。
4. README 和 examples 只展示 `on_bars`。

### Phase-2：账户快照与目标仓位

1. `Broker(initial_positions=...)`。
2. 初始持仓字段 `size/cost_price/available_size/locked_size`。
3. `initial_cash` 固定表示初始现金，不表示初始总权益。
4. `Broker.order_target_size/value/percent(...)`。

### Phase-3：市场特征模型

1. `SimpleMarket` 保持当前行为。
2. `MarketModel` 支持可交易时间、交易日、T+0/T+1、lot size、tick size、是否允许做空等特征。
3. `ChinaAStockMarket` 和 `CryptoMarket` 作为特征预设组合。
4. `close_position` 在 T+1 下默认全平失败，不静默部分平。

### Phase-4：函数式退出规则

1. `broker.add_exit_rule(...)`。
2. `stop_loss_pct(...)` 和 `take_profit_pct(...)`。
3. 退出规则使用当前价格和上一轮策略状态。

### Phase-5：最小限价单

1. pending limit order。
2. `cancel_order(order_id)`。
3. 基于 bar 的 high/low 成交判断。

### Phase-6：更多数据类型

只有真实需求出现时，再实现：

1. `on_books(dt, books)`。
2. `on_trades(dt, trades)`。
3. `on_news(dt, news)`。

## 当前尚未实现的设计能力

这些是设计目标，不代表当前代码已实现：

- `Strategy.on_bars(dt, bars)`。
- `Exchange.set_bars(...)`。
- `Broker(initial_positions=...)`。
- `Broker.order_target_size/value/percent(...)`。
- 函数式止盈止损。
- `MarketModel`、`SimpleMarket`、`ChinaAStockMarket`、`CryptoMarket`。
- `on_books/on_trades/on_news`。
- 限价单。
