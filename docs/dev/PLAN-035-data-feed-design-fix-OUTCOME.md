# PLAN-035 DataFeed 设计修正结果

## 完成内容

1. 重写 `docs/design/data-feed-20260701-design.md`。
2. 更新 `docs/design/README.md`，补充数据接入设计索引和第一阶段边界。
3. 明确第一阶段只做有限 replay feed，不实现 live feed。
4. 明确 `add_feed(replay_feed)` 第一阶段可以在 `run()` 时物化 events，并合并进现有 grouped 时间线。
5. 明确 `set_xx(...)` 和 `add_feed(...)` 共存时执行同一合并规则，重复 `(dt, symbol)` 直接报错。
6. 规范 `FeedEvent.dt` 对外类型为 `datetime.datetime`，SQLite 内部 `dt_ms` 不暴露给策略。
7. 移除公开 DataFeed 契约中的 `callback`、`priority`、`is_live`。
8. 明确第一阶段只支持标准事件类型 `bars/books/trades/news`，自定义事件放到后续阶段。
9. 明确同一 `dt, symbol` 多个价格源冲突时默认报错。
10. 补充 Binance BarsReplayFeed 参数、缓存模式、未闭合 K 线过滤和分页约束。
11. 补充 SQLite `source` 命名、coverage 半开区间、coverage merge 和 `refresh=True` 规则。

## 自审结论

本次修正解决了两份 review 中的核心问题：

1. 实时 feed 不再被纳入第一阶段，避免与当前预聚合 run loop 冲突。
2. `set_bars(...)` 与 `add_feed(...)` 的共存策略已明确。
3. `dt` 对外类型已规范，避免不同数据源导致策略回调类型漂移。
4. DataFeed 用户契约已收缩，避免过度设计。
5. 缓存和 Binance 实现关键边界已提前写清。

## 未实施内容

1. 未修改代码。
2. 未实现 `Exchange.add_feed(...)`。
3. 未实现 Binance 数据下载。
4. 未实现 SQLite 缓存。
5. 未实现 live feed。

## 后续建议

下一步如进入代码实施，建议按文档顺序先实现：

1. `FeedEvent`。
2. `Exchange.add_feed(feed)` 的 replay-only 版本。
3. `CsvBarsFeed` 或 `LocalBarsFeed`。
4. 再实现 `binance.BarsReplayFeed` 和 SQLite 缓存。
