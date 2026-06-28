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

